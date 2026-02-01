"""
Servicio Listener para dispositivos MQTT externos (ESP32, GRDs).
Se suscribe a topics configurados en la BD, normaliza los datos y los guarda.
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional

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

# Mapa en memoria: Topic -> Tag Object
# En producción, esto debería sincronizarse periódicamente
_topic_map: Dict[str, Tag] = {}

async def load_topic_map():
    """Carga los tags MQTT externos desde la base de datos."""
    global _topic_map
    try:
        async with async_session_factory() as session:
            stmt = select(Tag).options(selectinload(Tag.alarm_definition)).where(Tag.source_protocol == ProtocolType.MQTT)
            result = await session.execute(stmt)
            tags = result.scalars().all()
            
            new_map = {}
            for tag in tags:
                # La config debe tener "topic"
                # ej: {"topic": "sala1/temp", "json_key": "t"}
                config = tag.connection_config
                topic = config.get("topic")
                if topic:
                    new_map[topic] = tag
            
            _topic_map = new_map
            logger.info(f"Loaded {len(_topic_map)} external MQTT tags.")
            
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
                    logger.info(f"📡 Listening to external topic: {topic}")
                
                # Loop de mensajes
                async for message in client.messages:
                    await process_external_message(message)
                    
        except aiomqtt.MqttError as e:
            logger.error(f"MQTT Listener connection error: {e}. Reconnecting...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"MQTT Listener unexpected error: {e}")
            await asyncio.sleep(5)

async def process_external_message(message):
    """Procesa un mensaje de un dispositivo externo."""
    try:
        topic = str(message.topic)
        payload_str = message.payload.decode()
        
        # 1. Identificar tag
        # TODO: Soportar wildcards si fuera necesario
        tag = _topic_map.get(topic)
        if not tag:
            return # No configurado
            
        config = tag.connection_config
        
        # 2. Parsear valor
        value = 0.0
        json_key = config.get("json_key")
        
        try:
            if json_key:
                # Asumimos JSON: {"temp": 24.5}
                data = json.loads(payload_str)
                value = float(data.get(json_key, 0.0))
            else:
                # Raw value: "24.5"
                value = float(payload_str)
        except (ValueError, json.JSONDecodeError):
            logger.warning(f"Failed to parse payload from {topic}: {payload_str}")
            return

        # 3. Guardar en TimescaleDB
        await save_metric(tag_id=tag.id, value=value)
        
        # 4. Rebotar al sistema SCADA (Normalización)
        # Publicamos en el topic interno "scada/tags/..." para que el frontend lo vea
        # Si el tag tiene un mqtt_topic configurado, usamos ese.
        internal_topic = tag.mqtt_topic
        if not internal_topic:
            internal_topic = f"scada/tags/{tag.name}"
            
        payload = json.dumps({
            "tag_id": tag.id,
            "tag_name": tag.name,
            "value": value,
            "quality": "GOOD",
            #"timestamp": ... (opcional, si no el frontend pone now)
        })
        
        # Usamos el cliente global de publicación (para no bloquear el loop de escucha)
        await mqtt_client.publish(internal_topic, payload, qos=0)
        
        # 5. Evaluar Alarmas
        await alarm_engine.evaluate(tag, value)
        
    except Exception as e:
        logger.error(f"Error processing external MQTT message: {e}")
