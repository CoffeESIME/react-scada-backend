import asyncio
import json
# import logging  # Comentado temporalmente para reducir ruido
from datetime import datetime
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.db.models import Tag, ProtocolType  # Asegúrate de importar tu Enum
from app.services.bridges.factory import ProtocolFactory
from app.core.mqtt_client import mqtt_client
from app.services.alarms.engine import alarm_engine

# logger = logging.getLogger(__name__)  # Comentado temporalmente

# Tracks active per-tag polling tasks so we can cancel/restart them when tags change
_tag_tasks: dict[int, asyncio.Task] = {}

async def _poll_single_tag(tag_id: int, tag_name: str, protocol, connection_config: dict,
                           mqtt_topic: str, scan_rate_ms: int):
    """
    Coroutine que hace polling de un único tag en su propio intervalo (scan_rate_ms).
    Se ejecuta como Task independiente por cada tag activo.
    """
    interval = max(scan_rate_ms, 100) / 1000.0  # Mínimo 100ms, convertir a segundos
    print(f"🔄 [ENGINE] Tag '{tag_name}' (id={tag_id}) — scan_rate={scan_rate_ms}ms → interval={interval:.3f}s")

    while True:
        try:
            driver = ProtocolFactory.get_driver(protocol, connection_config)
            await driver.connect()
            raw_value = await driver.read_tag(connection_config)
            await driver.disconnect()

            if raw_value is not None:
                payload_dict = {
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "value": raw_value,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "quality": "GOOD"
                }

                topic = mqtt_topic or f"scada/tags/{tag_name}"
                await mqtt_client.publish(topic, json.dumps(payload_dict), qos=0)

                from app.services.storage import save_metric
                await save_metric(tag_id=tag_id, value=raw_value)

                # Re-fetch tag for alarm evaluation (lightweight — only alarm_definition)
                async with async_session_factory() as session:
                    stmt = select(Tag).options(selectinload(Tag.alarm_definition)).where(Tag.id == tag_id)
                    result = await session.execute(stmt)
                    tag_obj = result.scalars().first()
                if tag_obj:
                    await alarm_engine.evaluate(tag_obj, raw_value)

        except asyncio.CancelledError:
            print(f"🛑 [ENGINE] Task cancelada para tag '{tag_name}' (id={tag_id})")
            return
        except Exception as e:
            print(f"⚠️ [ENGINE] Error leyendo tag '{tag_name}': {e}")

        await asyncio.sleep(interval)


async def data_acquisition_loop():
    """
    Motor de Polling (Solicitud Activa).
    Lanza una Task independiente por cada tag activo no-MQTT,
    respetando su scan_rate_ms individual.
    Recarga la lista de tags cada 30 s para detectar cambios en caliente.
    """
    print("🚀 [ENGINE] Motor de Polling iniciado — scan_rate_ms por tag habilitado")

    while True:
        try:
            # 1. Cargar tags activos no-MQTT
            async with async_session_factory() as session:
                stmt = select(Tag).options(selectinload(Tag.alarm_definition)).where(
                    Tag.is_enabled == True,
                    Tag.source_protocol.in_([
                        ProtocolType.MODBUS,
                        ProtocolType.OPCUA,
                        ProtocolType.SIMULATED
                    ])
                )
                result = await session.execute(stmt)
                tags = result.scalars().all()

            current_ids = {t.id for t in tags}

            # 2. Cancelar tasks de tags que ya no existen o fueron deshabilitados
            for tid in list(_tag_tasks.keys()):
                if tid not in current_ids:
                    _tag_tasks[tid].cancel()
                    del _tag_tasks[tid]
                    print(f"🗑️ [ENGINE] Task removida para tag id={tid} (ya no activo)")

            # 3. Lanzar tasks para tags nuevos
            for tag in tags:
                if tag.id not in _tag_tasks or _tag_tasks[tag.id].done():
                    task = asyncio.create_task(
                        _poll_single_tag(
                            tag_id=tag.id,
                            tag_name=tag.name,
                            protocol=tag.source_protocol,
                            connection_config=tag.connection_config,
                            mqtt_topic=tag.mqtt_topic,
                            scan_rate_ms=tag.scan_rate_ms
                        ),
                        name=f"poll_tag_{tag.id}"
                    )
                    _tag_tasks[tag.id] = task

            if not tags:
                print("[ENGINE] No hay tags activos. Reintentando en 10s...")

        except Exception as e:
            print(f"🔥 [ENGINE] Error recargando tags: {e}")

        # Recargar configuración de tags cada 30 segundos
        await asyncio.sleep(30)