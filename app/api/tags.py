"""
Endpoints CRUD para gestión de Tags y Alarmas.
Incluye paginación, validación polimórfica y creación de alarmas embebidas.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.db.models import Tag, AlarmDefinition, ProtocolType
from app.schemas.tag import TagCreate, TagUpdate, TagRead, TagList, AlarmDefinitionRead

router = APIRouter(prefix="/tags", tags=["tags"])


# ============ CREATE ============

@router.post("/", response_model=TagRead, status_code=201)
async def create_tag(
    tag_data: TagCreate,
    session: AsyncSession = Depends(get_session)
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
    new_tag = Tag(**tag_dict)
    
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
    session: AsyncSession = Depends(get_session)
):
    """
    Lista paginada de Tags con filtros opcionales.
    """
    # Query base
    query = select(Tag).options(selectinload(Tag.alarm_definition))
    count_query = select(func.count(Tag.id))
    
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
    session: AsyncSession = Depends(get_session)
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
    
    return tag


# ============ UPDATE ============

@router.put("/{tag_id}", response_model=TagRead)
async def update_tag(
    tag_id: int,
    tag_data: TagUpdate,
    session: AsyncSession = Depends(get_session)
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
    session: AsyncSession = Depends(get_session)
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
    
    # Eliminar alarma primero si existe (o configurar cascade en el modelo)
    if tag.alarm_definition:
        await session.delete(tag.alarm_definition)
    
    await session.delete(tag)
    await session.commit()
    
    return None


# ============ Alarm-specific endpoints ============

@router.delete("/{tag_id}/alarm", status_code=204)
async def delete_tag_alarm(
    tag_id: int,
    session: AsyncSession = Depends(get_session)
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
    
    await session.delete(alarm)
    await session.commit()
    
    return None
