"""
Endpoints CRUD para gestión de Tags.

Cambios respecto a la arquitectura monolítica:
  - POST /tags y PUT /tags/{id}: tras el commit en BD, publican la configuración del
    tag en 'scada/edge/config/upsert' para que los nodos Edge carguen la nueva variable.
  - POST /tags/{id}/write: ya NO escala ni escribe directamente al PLC.
    Publica el comando en 'scada/edge/commands/write' y responde HTTP 202 Accepted,
    indicando que el comando fue encolado hacia el Edge para procesamiento asíncrono.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, or_
from sqlmodel import select
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.db.models import Tag, AlarmDefinition, ProtocolType, User
from app.users import current_active_user, current_admin_user
from app.core.mqtt_client import mqtt_client
from app.schemas.tag import TagCreate, TagUpdate, TagRead, TagList, AlarmDefinitionRead, TagWrite

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tags", tags=["tags"])


# ──────────────────────────────────────────────────────────────────────────────
# Helper: Publicar aprovisionamiento al Edge
# ──────────────────────────────────────────────────────────────────────────────

def _build_edge_tag_payload(tag: Tag) -> str:
    """
    Serializa un Tag a JSON listo para publicar en scada/edge/config/upsert.

    El Edge Node recibe esta estructura y actualiza su SQLite local:
    {
      "tags": [{
        "tag_id": 14,
        "tag_name": "NIVEL_TK01",
        "protocol": "modbus",
        "connection_config": {...},
        "scan_rate_ms": 1000,
        "mqtt_topic": "scada/tags/nivel_tk01",
        "is_enabled": true
      }]
    }
    """
    tag_dict = {
        "tag_id": tag.id,
        "tag_name": tag.name,
        "protocol": str(tag.source_protocol.value) if hasattr(tag.source_protocol, "value") else str(tag.source_protocol),
        "connection_config": tag.connection_config or {},
        "scan_rate_ms": tag.scan_rate_ms,
        "mqtt_topic": tag.mqtt_topic,
        "is_enabled": tag.is_enabled,
    }
    return json.dumps({"tags": [tag_dict]})


async def _provision_tag_to_edge(tag: Tag) -> None:
    """
    Publica la configuración del tag al tópico de aprovisionamiento del Edge.
    Se llama después de cada CREATE o UPDATE en la API REST.
    Es fire-and-forget: si falla el publish, se registra el error pero no
    revierte la transacción de BD (el reintento vendrá del reload periódico del Edge).

    Publica en DOS tópicos para garantizar entrega:
      1. scada/edge/config/upsert          → Broadcast: todos los Edges lo reciben.
      2. scada/edge/+/config/upsert        → No se puede publicar en wildcard.

    Nota: el Edge se suscribe a scada/edge/{EDGE_ID}/config/upsert (específico)
    Y también a scada/edge/config/upsert (broadcast) — ver _listener_task en edge_engine.py.
    """
    # Tópico broadcast: todos los Edges reciben la actualización.
    broadcast_topic = "scada/edge/config/upsert"
    try:
        payload = _build_edge_tag_payload(tag)
        await mqtt_client.publish(broadcast_topic, payload, qos=1)
        logger.info(
            "[TAGS] Tag '%s' (id=%d) aprovisionado → %s",
            tag.name, tag.id, broadcast_topic,
        )
    except Exception as exc:
        logger.error(
            "[TAGS] Error publicando aprovisionamiento del tag '%s': %s. "
            "El Edge lo cargará en su próximo reload periódico.",
            tag.name, exc,
        )


# ──────────────────────────────────────────────────────────────────────────────
# POST /tags — Crear Tag
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/", response_model=TagRead, status_code=201)
async def create_tag(
    tag_data: TagCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user),
):
    """
    Crea un nuevo Tag.
    1. Persiste en PostgreSQL/TimescaleDB.
    2. Publica la configuración en 'scada/edge/config/upsert' para notificar al Edge.
    """
    # Verificar unicidad del nombre.
    existing = await session.execute(select(Tag).where(Tag.name == tag_data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Ya existe un tag con el nombre '{tag_data.name}'",
        )

    # Crear Tag y (opcionalmente) su AlarmDefinition en una transacción.
    tag_dict = tag_data.model_dump(exclude={"alarm"})
    new_tag = Tag(**tag_dict, owner_id=user.id)
    session.add(new_tag)
    await session.flush()  # Obtener el ID generado.

    if tag_data.alarm:
        alarm_def = AlarmDefinition(tag_id=new_tag.id, **tag_data.alarm.model_dump())
        session.add(alarm_def)

    await session.commit()
    await session.refresh(new_tag)

    # Recargar con relaciones para la respuesta.
    result = await session.execute(
        select(Tag).options(selectinload(Tag.alarm_definition)).where(Tag.id == new_tag.id)
    )
    tag_with_alarm = result.scalar_one()

    # ── APROVISIONAMIENTO DINÁMICO: Notificar al Edge ────────────────────────
    # Fire-and-forget: el Edge se enterará de este nuevo tag vía MQTT.
    await _provision_tag_to_edge(tag_with_alarm)

    return tag_with_alarm


# ──────────────────────────────────────────────────────────────────────────────
# GET /tags — Listar Tags (paginado)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/", response_model=TagList)
async def list_tags(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    protocol: Optional[ProtocolType] = None,
    is_enabled: Optional[bool] = None,
    search: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
):
    """Lista paginada de Tags con filtros opcionales."""
    query = (
        select(Tag)
        .options(selectinload(Tag.alarm_definition))
        .where(or_(Tag.owner_id == user.id, Tag.owner_id.is_(None)))
    )
    count_query = select(func.count(Tag.id)).where(
        or_(Tag.owner_id == user.id, Tag.owner_id.is_(None))
    )

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

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Tag.id)
    result = await session.execute(query)
    tags = result.scalars().all()

    pages = (total + page_size - 1) // page_size if total > 0 else 1
    return TagList(items=tags, total=total, page=page, page_size=page_size, pages=pages)


# ──────────────────────────────────────────────────────────────────────────────
# GET /tags/{tag_id} — Detalle de Tag
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/{tag_id}", response_model=TagRead)
async def get_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
):
    """Obtiene el detalle de un Tag por ID, incluyendo su alarma si existe."""
    result = await session.execute(
        select(Tag).options(selectinload(Tag.alarm_definition)).where(Tag.id == tag_id)
    )
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")
    if tag.owner_id is not None and tag.owner_id != user.id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este tag")
    return tag


# ──────────────────────────────────────────────────────────────────────────────
# POST /tags/{tag_id}/reprovision — Re-publicar config de un tag al Edge
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/{tag_id}/reprovision", status_code=200)
async def reprovision_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user),
):
    """
    Re-publica la configuración de un tag existente al tópico MQTT de aprovisionamiento.

    Útil cuando:
      - El Edge se reinició y su SQLite quedó vacío.
      - Hubo un error de entrega en el publish original.
      - Se necesita forzar la sincronización sin modificar el tag.
    """
    result = await session.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")

    await _provision_tag_to_edge(tag)
    return {
        "status": "published",
        "tag_id": tag.id,
        "tag_name": tag.name,
        "topic": "scada/edge/config/upsert",
    }


@router.post("/reprovision/all", status_code=200)
async def reprovision_all_tags(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user),
):
    """
    Re-publica TODOS los tags activos al tópico de aprovisionamiento del Edge.

    Útil como operación de sincronización masiva después de un reinicio del Edge
    o para poblar un nuevo nodo Edge con la configuración actual del sistema.
    """
    result = await session.execute(
        select(Tag).where(Tag.is_enabled == True).order_by(Tag.id)
    )
    tags = result.scalars().all()

    published = []
    failed = []
    for tag in tags:
        try:
            await _provision_tag_to_edge(tag)
            published.append({"tag_id": tag.id, "tag_name": tag.name})
        except Exception as exc:
            failed.append({"tag_id": tag.id, "tag_name": tag.name, "error": str(exc)})

    return {
        "status": "completed",
        "published_count": len(published),
        "failed_count": len(failed),
        "published": published,
        "failed": failed,
        "topic": "scada/edge/config/upsert",
    }




# ──────────────────────────────────────────────────────────────────────────────
# POST /tags/{tag_id}/write — Escritura Asíncrona (Pub/Sub → Edge)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/{tag_id}/write", status_code=202)
async def write_tag_value(
    tag_id: int,
    write_data: TagWrite,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user),
):
    """
    Envía un comando de escritura al dispositivo de campo VÍA MQTT (async).

    Flujo:
      1. Valida que el tag exista y tenga acceso de escritura (W o RW).
      2. Publica el comando JSON en 'scada/edge/commands/write'.
      3. Responde HTTP 202 Accepted — el comando fue encolado, no ejecutado aún.

    El Edge Node procesa el mensaje, escribe en el PLC y publica el ACK en
    'scada/edge/{edge_id}/commands/write/ack'.

    NOTA: Ya NO existe lógica de escalado inverso en el backend. Si se requiere
    escalado, debe configurarse en el Edge Node o en la UI antes de enviar.
    """
    # ── Validar tag ───────────────────────────────────────────────────────────
    result = await session.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()

    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")
    if tag.owner_id is not None and tag.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el dueño puede escribir en este tag")
    if tag.access_mode == "R":
        raise HTTPException(
            status_code=400,
            detail=f"El tag '{tag.name}' es de solo lectura (access_mode=R)",
        )

    # ── Formar comando para el Edge ───────────────────────────────────────────
    command_payload = json.dumps({
        "tag_id":           tag.id,
        "tag_name":         tag.name,
        "value":            write_data.value,
        "protocol":         str(tag.source_protocol.value) if hasattr(tag.source_protocol, "value") else str(tag.source_protocol),
        "connection_config": tag.connection_config or {},
        "requested_by":     user.email,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
    })

    # ── Publicar en MQTT (fire-and-forget hacia el Edge) ─────────────────────
    write_topic = "scada/edge/commands/write"
    published = await mqtt_client.publish(write_topic, command_payload, qos=1)

    if not published:
        raise HTTPException(
            status_code=503,
            detail="No se pudo encolar el comando: el cliente MQTT no está conectado al broker.",
        )

    logger.info(
        "[TAGS] Comando de escritura encolado → tag='%s' (id=%d) value=%s topic=%s",
        tag.name, tag.id, write_data.value, write_topic,
    )

    # HTTP 202 Accepted: el comando fue recibido y encolado hacia el Edge.
    return {
        "status": "accepted",
        "message": "Comando encolado para procesamiento asíncrono en el Edge Node.",
        "tag_id":   tag.id,
        "tag_name": tag.name,
        "value":    write_data.value,
        "topic":    write_topic,
    }


# ──────────────────────────────────────────────────────────────────────────────
# PUT /tags/{tag_id} — Actualizar Tag
# ──────────────────────────────────────────────────────────────────────────────

@router.put("/{tag_id}", response_model=TagRead)
async def update_tag(
    tag_id: int,
    tag_data: TagUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user),
):
    """
    Actualiza un Tag existente.
    1. Persiste los cambios en BD.
    2. Publica la nueva configuración en 'scada/edge/config/upsert' para notificar al Edge.
    """
    result = await session.execute(
        select(Tag).options(selectinload(Tag.alarm_definition)).where(Tag.id == tag_id)
    )
    tag = result.scalar_one_or_none()

    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")
    if tag.owner_id is not None and tag.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el dueño puede actualizar este tag")

    # Verificar unicidad si se cambia el nombre.
    if tag_data.name and tag_data.name != tag.name:
        existing = await session.execute(select(Tag).where(Tag.name == tag_data.name))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Ya existe un tag con el nombre '{tag_data.name}'",
            )

    # Aplicar cambios del Tag.
    update_dict = tag_data.model_dump(exclude={"alarm"}, exclude_unset=True)
    for field, value in update_dict.items():
        setattr(tag, field, value)

    # Actualizar o crear AlarmDefinition si se incluyó.
    if tag_data.alarm:
        if tag.alarm_definition:
            for field, value in tag_data.alarm.model_dump().items():
                setattr(tag.alarm_definition, field, value)
        else:
            alarm_def = AlarmDefinition(tag_id=tag.id, **tag_data.alarm.model_dump())
            session.add(alarm_def)

    await session.commit()

    # Recargar con relaciones.
    result = await session.execute(
        select(Tag).options(selectinload(Tag.alarm_definition)).where(Tag.id == tag_id)
    )
    updated_tag = result.scalar_one()

    # ── APROVISIONAMIENTO DINÁMICO: Notificar al Edge ────────────────────────
    await _provision_tag_to_edge(updated_tag)

    return updated_tag


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /tags/{tag_id} — Eliminar Tag
# ──────────────────────────────────────────────────────────────────────────────

@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user),
):
    """
    Elimina un Tag y su AlarmDefinition asociada (cascade).
    El Edge dejará de leer el tag en su próximo reload de caché (30s).
    """
    result = await session.execute(
        select(Tag).options(selectinload(Tag.alarm_definition)).where(Tag.id == tag_id)
    )
    tag = result.scalar_one_or_none()

    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")
    if tag.owner_id is not None and tag.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el dueño puede eliminar este tag")

    if tag.alarm_definition:
        await session.delete(tag.alarm_definition)

    from app.db.models import Metric
    from sqlmodel import delete
    await session.execute(delete(Metric).where(Metric.tag_id == tag_id))

    await session.delete(tag)
    await session.commit()
    return None


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /tags/{tag_id}/alarm — Eliminar solo la alarma de un Tag
# ──────────────────────────────────────────────────────────────────────────────

@router.delete("/{tag_id}/alarm", status_code=204)
async def delete_tag_alarm(
    tag_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_admin_user),
):
    """Elimina solo la AlarmDefinition de un Tag (sin eliminar el Tag)."""
    result = await session.execute(
        select(AlarmDefinition).where(AlarmDefinition.tag_id == tag_id)
    )
    alarm = result.scalar_one_or_none()

    if not alarm:
        raise HTTPException(status_code=404, detail="Este tag no tiene alarma definida")

    tag_res = await session.execute(select(Tag).where(Tag.id == tag_id))
    tag = tag_res.scalar_one_or_none()
    if tag and tag.owner_id is not None and tag.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el dueño puede eliminar la alarma")

    await session.delete(alarm)
    await session.commit()
    return None
