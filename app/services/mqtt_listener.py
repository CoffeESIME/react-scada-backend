"""
Servicio Listener para dispositivos MQTT externos (ESP32, GRDs).
Se suscribe a topics configurados en la BD, normaliza los datos y los guarda.
"""
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional

import aiomqtt
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.mqtt_client import mqtt_client
from app.db.session import async_session_factory
from app.db.models import Tag, ProtocolType
from app.services.storage import save_metric
from app.services.alarms.engine import alarm_engine

logger = logging.getLogger(__name__)

# Mapa en memoria: Topic -> Lista de Tags (soporta múltiples tags por topic)
_topic_map: Dict[str, List[Tag]] = {}

async def load_topic_map():
    """Carga los tags MQTT externos desde la base de datos."""
    global _topic_map
    try:
        async with async_session_factory() as session:
            stmt = select(Tag).options(selectinload(Tag.alarm_definition)).where(Tag.source_protocol == ProtocolType.MQTT)
            result = await session.execute(stmt)
            tags = result.scalars().all()
            
            new_map: Dict[str, List[Tag]] = {}
            for tag in tags:
                # La config debe tener "topic"
                # ej: {"topic": "sala1/temp", "json_key": "t"}
                config = tag.connection_config
                topic = config.get("topic")
                if topic:
                    if topic not in new_map:
                        new_map[topic] = []
                    new_map[topic].append(tag)
            
            _topic_map = new_map
            total_tags = sum(len(tags) for tags in _topic_map.values())
            logger.info(f"Loaded {total_tags} external MQTT tags across {len(_topic_map)} topics.")
            
    except Exception as e:
        logger.error(f"Error loading topic map: {e}")

async def start_mqtt_listener():
    """
    Loop principal del Listener de MQTT Externo.
    1. Carga configs.
    2. Suscribe.
    3. Procesa mensajes entrantes.
    """
    logger.info("🚀 Iniciando MQTT Listener (External Devices)...")
    
    # Cargar mapa inicial
    await load_topic_map()
    
    # Iniciar tarea de refresco periódico del mapa
    asyncio.create_task(_periodic_topic_refresh())
    
    while True:
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_broker_host,
                port=settings.mqtt_broker_port,
                username=settings.mqtt_username,
                password=settings.mqtt_password,
                identifier=f"{settings.mqtt_client_id}-listener"
            ) as client:
                
                # Suscribirse a los topics detectados
                if not _topic_map:
                    logger.warning("No external MQTT tags configured. Waiting...")
                    await asyncio.sleep(10)
                    await load_topic_map() # Reintentar carga
                    continue

                for topic in _topic_map.keys():
                    await client.subscribe(topic)
                    tags_on_topic = _topic_map[topic]
                    logger.info(f"📡 Listening to external topic: {topic} ({len(tags_on_topic)} tags)")
                
                # Loop de mensajes
                async for message in client.messages:
                    await process_external_message(message)
                    
        except aiomqtt.MqttError as e:
            logger.error(f"MQTT Listener connection error: {e}. Reconnecting...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"MQTT Listener unexpected error: {e}")
            await asyncio.sleep(5)

async def _periodic_topic_refresh():
    """Recarga el mapa de topics cada 30 segundos para detectar cambios."""
    while True:
        await asyncio.sleep(30)  # Refrescar cada 30 segundos
        logger.info("[MQTT LISTENER] Refrescando mapa de topics...")
        await load_topic_map()
        total_tags = sum(len(tags) for tags in _topic_map.values())
        logger.info(f"[MQTT LISTENER] Topics actuales: {list(_topic_map.keys())} ({total_tags} tags total)")

async def process_external_message(message):
    """Procesa un mensaje de un dispositivo externo."""
    try:
        topic = str(message.topic)
        payload_str = message.payload.decode()
        
        logger.info(f"[MQTT DEBUG] 📩 Mensaje recibido en: {topic}")
        logger.info(f"[MQTT DEBUG] 📦 Payload: {payload_str[:200]}")
        
        # 1. Obtener lista de tags para este topic
        tags = _topic_map.get(topic)
        if not tags:
            logger.warning(f"[MQTT DEBUG] ⚠️ Topic '{topic}' NO está en el mapa de tags. Topics configurados: {list(_topic_map.keys())}")
            return
        
        logger.info(f"[MQTT DEBUG] ✅ {len(tags)} tag(s) encontrado(s) para este topic")
        
        # Parsear el payload una sola vez
        parsed_data = None
        try:
            parsed_data = json.loads(payload_str)
        except json.JSONDecodeError:
            # No es JSON, se tratará como valor raw
            pass
        
        # 2. Procesar cada tag asociado a este topic
        for tag in tags:
            await _process_tag_value(tag, payload_str, parsed_data)
                
    except Exception as e:
        logger.error(f"[MQTT DEBUG] ❌ Error processing external MQTT message: {e}")


async def _process_tag_value(tag: Tag, payload_str: str, parsed_data: Optional[dict]):
    """Procesa el valor para un tag específico."""
    try:
        config = tag.connection_config
        json_key = config.get("json_key")
        
        logger.info(f"[MQTT DEBUG] 🏷️ Procesando tag: id={tag.id}, name={tag.name}, json_key={json_key}")
        
        # Extraer valor
        value = 0.0
        if json_key and parsed_data:
            # Extraer valor del JSON
            value = float(parsed_data.get(json_key, 0.0))
            logger.info(f"[MQTT DEBUG] 📊 Valor extraído (json_key={json_key}): {value}")
        elif parsed_data is None:
            # Raw value
            value = float(payload_str)
            logger.info(f"[MQTT DEBUG] 📊 Valor raw: {value}")
        else:
            # JSON pero sin json_key especificado - intentar usar el primer valor numérico
            for k, v in parsed_data.items():
                try:
                    value = float(v)
                    logger.info(f"[MQTT DEBUG] 📊 Usando primer valor numérico del JSON ({k}): {value}")
                    break
                except (ValueError, TypeError):
                    continue
        
        # 3. Guardar en TimescaleDB
        logger.info(f"[MQTT DEBUG] 💾 Guardando métrica: tag_id={tag.id}, value={value}")
        await save_metric(tag_id=tag.id, value=value)
        
        # 4. Publicar al topic interno para el frontend
        internal_topic = tag.mqtt_topic
        if not internal_topic:
            internal_topic = f"scada/tags/{tag.name}"
            
        payload = json.dumps({
            "tag_id": tag.id,
            "tag_name": tag.name,
            "value": value,
            "quality": "GOOD",
        })
        
        logger.info(f"[MQTT DEBUG] 📤 Publicando a topic interno: {internal_topic}")
        await mqtt_client.publish(internal_topic, payload, qos=0)
        
        # 5. Evaluar Alarmas
        await alarm_engine.evaluate(tag, value)
        
    except Exception as e:
        logger.error(f"[MQTT DEBUG] ❌ Error procesando tag {tag.name}: {e}")

