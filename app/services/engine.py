"""
Motor de adquisición de datos.
Corre en background y orquesta la lectura de tags usando la Factory de Drivers.
"""
import asyncio
import json
import logging
from datetime import datetime
from sqlalchemy import select

from app.db.session import async_session_factory
from app.db.models import Tag, ProtocolType
from app.services.bridges.factory import ProtocolFactory
from app.core.mqtt_client import mqtt_client

logger = logging.getLogger(__name__)

async def data_acquisition_loop():
    """
    Loop principal de adquisición de datos.
    1. Lee Tags habilitados de la DB.
    2. Instancia drivers vía Factory.
    3. Lee valores.
    4. Publica en MQTT.
    """
    logger.info("🚀 Iniciando Motor de Adquisición de Datos...")
    
    # Cache simple de drivers para no reconectar en cada ciclo
    # Key: protocol_type + hash(config)  (Simplificación)
    # En una implementación real, agruparíamos tags por "device"
    
    while True:
        try:
            async with async_session_factory() as session:
                # 1. Obtener Tags habilitados
                stmt = select(Tag).where(Tag.is_enabled == True)
                result = await session.execute(stmt)
                tags = result.scalars().all()

            if not tags:
                # Si no hay tags, esperar un poco más
                await asyncio.sleep(5)
                continue

            # 2. Iterar y Leer
            # TODO: Optimizar con asyncio.gather para paralelismo real
            for tag in tags:
                try:
                    # Instanciamos el driver adecuado usando la FACTORY
                    # NOTA: Esto crea una nueva conexión por cada tag por cada loop.
                    # Es ineficiente para Modbus/TCP. Se debería cachear el driver
                    # basado en la conexión (IP/Port), no en el tag.
                    # Para esta iteración, seguimos el diseño simple.
                    
                    protocol = tag.source_protocol
                    if isinstance(protocol, ProtocolType):
                        protocol = protocol.value
                        
                    driver = ProtocolFactory.get_driver(
                        protocol, 
                        tag.connection_config
                    )
                    
                    # Leemos el valor
                    raw_value = await driver.read_tag(tag.connection_config)
                    
                    # Cerramos conexión (Ineficiente, pero seguro para MVP)
                    await driver.disconnect()
                    
                    if raw_value is not None:
                        # 3. Normalizar Payload
                        payload = json.dumps({
                            "tag_id": tag.id,
                            "tag_name": tag.name,
                            "value": raw_value,
                            "timestamp": datetime.utcnow().isoformat(),
                            "quality": "GOOD"
                        })
                        
                        # 4. Publicar a MQTT
                        # Topic: scada/tags/Tanque1
                        # Aseguramos que el topic exista en el tag o usamos uno por defecto
                        topic = tag.mqtt_topic
                        if not topic:
                            topic = f"scada/tags/{tag.name}"
                            
                        await mqtt_client.publish(topic, payload, qos=0)
                            
                except Exception as e:
                    logger.error(f"Error procesando tag {tag.name}: {e}")

            # Esperar antes del siguiente barrido
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error crítico en loop de adquisición: {e}")
            await asyncio.sleep(5) # Esperar antes de reintentar si cae la DB
