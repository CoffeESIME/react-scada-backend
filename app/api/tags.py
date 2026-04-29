"""
Endpoints CRUD para gestión de Tags y Alarmas.
Incluye paginación, validación polimórfica y creación de alarmas embebidas.
"""
import json
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func, or_

from app.db.session import get_session
from app.db.models import Tag, AlarmDefinition, ProtocolType, User
from app.users import current_active_user, current_admin_user
from app.core.mqtt_client import mqtt_client
from app.schemas.tag import TagCreate, TagUpdate, TagRead, TagList, AlarmDefinitionRead, TagWrite
from app.services.bridges.factory import ProtocolFactory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tags", tags=["tags"])


# ============ CREATE ============

@router.post("/", response_model=TagRead, status_code=201)
async def create_tag(
    tag_data: TagCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user)
):
    """
    Crea un nuevo Tag.
    Si incluye 'alarm', también crea la AlarmDefinition en la misma transacción.
    """
    # Verificar nombre duplicado
    existing = await session.execute(
        select(Tag).where(Tag.name == tag_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Ya existe un tag con el nombre '{tag_data.name}'"
        )
    
    # Crear Tag (excluyendo 'alarm' que no es parte del modelo)
    tag_dict = tag_data.model_dump(exclude={"alarm"})
    new_tag = Tag(**tag_dict, owner_id=user.id)
    
    session.add(new_tag)
    await session.flush()  # Para obtener el ID antes del commit
    
    # Si hay datos de alarma, crear AlarmDefinition
    if tag_data.alarm:
        alarm_def = AlarmDefinition(
            tag_id=new_tag.id,
            **tag_data.alarm.model_dump()
        )
        session.add(alarm_def)
    
    await session.commit()
    await session.refresh(new_tag)
    
    # Cargar relación de alarma para la respuesta
    result = await session.execute(
        select(Tag)
        .options(selectinload(Tag.alarm_definition))
        .where(Tag.id == new_tag.id)
    )
    tag_with_alarm = result.scalar_one()
    
    return tag_with_alarm


# ============ READ (List) ============

@router.get("/", response_model=TagList)
async def list_tags(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    protocol: Optional[ProtocolType] = None,
    is_enabled: Optional[bool] = None,
    search: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user)
):
    """
    Lista paginada de Tags con filtros opcionales.
    """
    # Query base filtrando por dueño
    query = select(Tag).options(selectinload(Tag.alarm_definition)).where(
        or_(Tag.owner_id == user.id, Tag.owner_id.is_(None))
    )
    count_query = select(func.count(Tag.id)).where(
        or_(Tag.owner_id == user.id, Tag.owner_id.is_(None))
    )
    
    # Filtros
    if protocol:
        query = query.where(Tag.source_protocol == protocol)
        count_query = count_query.where(Tag.source_protocol == protocol)
    
    if is_enabled is not None:
        query = query.where(Tag.is_enabled == is_enabled)
        count_query = count_query.where(Tag.is_enabled == is_enabled)
    
    if search:
        search_filter = Tag.name.ilike(f"%{search}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
    
    # Contar total
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0
    
    # Paginación
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Tag.id)
    
    result = await session.execute(query)
    tags = result.scalars().all()
    
    # Calcular páginas
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return TagList(
        items=tags,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages
    )


# ============ READ (Detail) ============

@router.get("/{tag_id}", response_model=TagRead)
async def get_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user)
):
    """
    Obtiene el detalle de un Tag por ID, incluyendo su alarma si existe.
    """
    result = await session.execute(
        select(Tag)
        .options(selectinload(Tag.alarm_definition))
        .where(Tag.id == tag_id)
    )
    tag = result.scalar_one_or_none()
    
    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")
        
    if tag.owner_id is not None and tag.owner_id != user.id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este tag")
    
    return tag


# ============ WRITE (Command) ============

def _apply_inverse_scaling(value: float, scaling: dict) -> float:
    """Aplica escalado inverso: convierte el valor UI al valor raw del dispositivo."""
    scale_type = scaling.get("type", "none")
    
    if scale_type == "multiplier":
        factor = float(scaling.get("multiplier_factor", 1.0))
        if factor == 0:
            raise ValueError("multiplier_factor no puede ser 0")
        return value / factor
    
    elif scale_type == "linear":
        cfg = scaling.get("linear_config", {})
        raw_min = float(cfg.get("raw_min", 0))
        raw_max = float(cfg.get("raw_max", 27648))
        scaled_min = float(cfg.get("scaled_min", 0.0))
        scaled_max = float(cfg.get("scaled_max", 100.0))
        
        if scaled_max == scaled_min:
            raise ValueError("scaled_min y scaled_max no pueden ser iguales")
        
        # Ecuación de la recta inversa: raw = raw_min + (value - scaled_min) * (raw_max - raw_min) / (scaled_max - scaled_min)
        raw_value = raw_min + (value - scaled_min) * (raw_max - raw_min) / (scaled_max - scaled_min)
        return raw_value
    
    # "none" o cualquier otro: pasar tal cual
    return value


@router.post("/{tag_id}/write", status_code=200)
async def write_tag_value(
    tag_id: int,
    write_data: TagWrite,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user)
):
    """
    Escribe un valor en un Tag.
    1. Valida access_mode (debe ser W o RW).
    2. Aplica escalado inverso si aplica.
    3. Usa ProtocolFactory para escribir al dispositivo físico.
    4. Publica el valor escalado en MQTT para feedback UI.
    """
    # 1. Buscar Tag
    result = await session.execute(
        select(Tag).where(Tag.id == tag_id)
    )
    tag = result.scalar_one_or_none()
    
    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")
    
    if tag.owner_id is not None and tag.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el dueño puede escribir en este tag")
    
    # 2. Validar modo de acceso
    if tag.access_mode == 'R':
        raise HTTPException(
            status_code=400,
            detail=f"El tag '{tag.name}' es de solo lectura (access_mode=R)"
        )
    
    # 3. Escalado inverso
    scaling = tag.connection_config.get("scaling", {"type": "none"})
    try:
        raw_value = _apply_inverse_scaling(float(write_data.value), scaling)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Error de escalado: {e}")
    
    # Cast según data_type
    if tag.data_type == 'boolean':
        final_value = bool(raw_value)
    elif tag.data_type == 'integer':
        final_value = int(round(raw_value))
    else:
        final_value = float(raw_value)
    
    logger.info(f"[WRITE] Tag {tag.id} ({tag.name}): UI={write_data.value} -> raw={final_value} (scaling={scaling.get('type','none')})")
    
    # 4. Escribir al dispositivo usando el ProtocolFactory
    write_success = False
    write_error = None
    
    try:
        driver = ProtocolFactory.get_driver(tag.source_protocol, tag.connection_config)
        connected = await driver.connect()
        
        if not connected:
            raise ConnectionError(f"No se pudo conectar al dispositivo ({tag.source_protocol})")
        
        write_success = await driver.write_tag(tag.connection_config, final_value)
        await driver.disconnect()
        
        if not write_success:
            raise IOError(f"El driver reportó fallo al escribir en el registro")
            
    except (ValueError, ConnectionError, IOError) as e:
        write_error = str(e)
        raise HTTPException(status_code=502, detail=f"Error de escritura en campo: {write_error}")
    except Exception as e:
        write_error = str(e)
        logger.error(f"[WRITE] Error inesperado: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno al escribir: {write_error}")
    
    # 5. Publicar valor escalado (UI) en MQTT para feedback en tiempo real
    mqtt_payload = {
        "tag_id": tag.id,
        "tag_name": tag.name,
        "value": float(write_data.value),  # Valor legible para el operador
        "raw_value": final_value,
        "timestamp": datetime.utcnow().isoformat(),
        "quality": "MANUAL_WRITE"
    }
    await mqtt_client.publish(tag.mqtt_topic, json.dumps(mqtt_payload), qos=1)
    
    return {
        "status": "ok",
        "tag_id": tag.id,
        "tag_name": tag.name,
        "value_written": float(write_data.value),
        "raw_sent": final_value,
        "scaling_applied": scaling.get("type", "none")
    }


# ============ UPDATE ============

@router.put("/{tag_id}", response_model=TagRead)
async def update_tag(
    tag_id: int,
    tag_data: TagUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user)
):
    """
    Actualiza un Tag existente.
    Si incluye 'alarm', actualiza o crea la AlarmDefinition.
    """
    # Buscar tag existente
    result = await session.execute(
        select(Tag)
        .options(selectinload(Tag.alarm_definition))
        .where(Tag.id == tag_id)
    )
    tag = result.scalar_one_or_none()
    
    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")
        
    if tag.owner_id is not None and tag.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el dueño puede actualizar este tag")
    
    # Verificar nombre duplicado si se está actualizando
    if tag_data.name and tag_data.name != tag.name:
        existing = await session.execute(
            select(Tag).where(Tag.name == tag_data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Ya existe un tag con el nombre '{tag_data.name}'"
            )
    
    # Actualizar campos del tag (solo los proporcionados)
    update_dict = tag_data.model_dump(exclude={"alarm"}, exclude_unset=True)
    for field, value in update_dict.items():
        setattr(tag, field, value)
    
    # Manejar alarma
    if tag_data.alarm:
        if tag.alarm_definition:
            # Actualizar alarma existente
            for field, value in tag_data.alarm.model_dump().items():
                setattr(tag.alarm_definition, field, value)
        else:
            # Crear nueva alarma
            alarm_def = AlarmDefinition(
                tag_id=tag.id,
                **tag_data.alarm.model_dump()
            )
            session.add(alarm_def)
    
    await session.commit()
    await session.refresh(tag)
    
    # Recargar con relación
    result = await session.execute(
        select(Tag)
        .options(selectinload(Tag.alarm_definition))
        .where(Tag.id == tag_id)
    )
    
    return result.scalar_one()


# ============ DELETE ============

@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user)
):
    """
    Elimina un Tag y su AlarmDefinition asociada (cascade).
    """
    result = await session.execute(
        select(Tag)
        .options(selectinload(Tag.alarm_definition))
        .where(Tag.id == tag_id)
    )
    tag = result.scalar_one_or_none()
    
    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")
        
    if tag.owner_id is not None and tag.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el dueño puede eliminar este tag")
    
    # Eliminar alarma primero si existe (o configurar cascade en el modelo)
    if tag.alarm_definition:
        await session.delete(tag.alarm_definition)
        
    # Eliminar historial asociado (metrics)
    from app.db.models import Metric
    from sqlmodel import delete
    await session.execute(
        delete(Metric).where(Metric.tag_id == tag_id)
    )
    
    await session.delete(tag)
    await session.commit()
    
    return None


# ============ Alarm-specific endpoints ============

@router.delete("/{tag_id}/alarm", status_code=204)
async def delete_tag_alarm(
    tag_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user)
):
    """
    Elimina solo la AlarmDefinition de un Tag (sin eliminar el Tag).
    """
    result = await session.execute(
        select(AlarmDefinition).where(AlarmDefinition.tag_id == tag_id)
    )
    alarm = result.scalar_one_or_none()
    
    
    if not alarm:
        raise HTTPException(status_code=404, detail="Este tag no tiene alarma definida")
        
    # Verificar ownership del tag
    tag_res = await session.execute(select(Tag).where(Tag.id == tag_id))
    tag = tag_res.scalar_one_or_none()
    if tag and tag.owner_id is not None and tag.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el dueño puede eliminar la alarma")
    
    await session.delete(alarm)
    await session.commit()
    
    return None
