import asyncio
import json
import logging
from datetime import datetime
from sqlalchemy import select, or_

from app.db.session import async_session_factory
from app.db.models import Tag, ProtocolType  # Asegúrate de importar tu Enum
from app.services.bridges.factory import ProtocolFactory
from app.core.mqtt_client import mqtt_client

logger = logging.getLogger(__name__)

async def data_acquisition_loop():
    """
    Motor de Polling (Solicitud Activa).
    SOLO procesa protocolos que requieren interrogación: Modbus, OPC UA, Simulación.
    IGNORA protocolos pasivos como MQTT (esos los maneja el mqtt_listener).
    """
    logger.info("🚀 Iniciando Motor de Polling (Modbus/OPCUA/Sim)...")
    
    while True:
        try:
            async with async_session_factory() as session:
                # 1. FILTRADO INTELIGENTE
                # Solo traemos tags habilitados Y que NO sean MQTT
                stmt = select(Tag).where(
                    Tag.is_enabled == True,
                    Tag.source_protocol.in_([
                        ProtocolType.MODBUS, 
                        ProtocolType.OPCUA, 
                        ProtocolType.SIMULATED
                    ])
                    # Alternativa: Tag.source_protocol != ProtocolType.MQTT
                )
                
                result = await session.execute(stmt)
                tags = result.scalars().all()

            if not tags:
                # Si no hay nada que leer, dormimos más para ahorrar CPU
                await asyncio.sleep(5)
                continue

            # 2. Iterar y Leer
            for tag in tags:
                try:
                    # Instanciamos el driver
                    driver = ProtocolFactory.get_driver(
                        tag.source_protocol, 
                        tag.connection_config
                    )
                    
                    # Conexión (Idealmente cacheada, aquí on-demand para MVP)
                    await driver.connect() 
                    
                    # Leemos el valor
                    raw_value = await driver.read_tag(tag.connection_config)
                    
                    # Cerramos conexión
                    await driver.disconnect()
                    
                    if raw_value is not None:
                        # 3. Normalizar Payload
                        payload_dict = {
                            "tag_id": tag.id,
                            "tag_name": tag.name,
                            "value": raw_value,
                            "timestamp": datetime.utcnow().isoformat(),
                            "quality": "GOOD"
                        }
                        
                        # 4. Publicar a MQTT (Topic Interno del SCADA)
                        # El frontend se suscribe a esto.
                        topic = tag.mqtt_topic
                        
                        # Publicamos (Fire and forget)
                        await mqtt_client.publish(topic, json.dumps(payload_dict), qos=0)
                        
                        # OJO: Aquí NO guardamos en SQL todavía.
                        # Dejamos que el servicio de "History Subscriber" lo haga
                        # para no bloquear este loop de lectura.
                            
                except Exception as e:
                    logger.error(f"⚠️ Error leyendo tag {tag.name}: {e}")

            # Scan Rate Global (Simplificado para MVP)
            # En producción, cada tag debería tener su propio timer.
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"🔥 Error crítico en loop de adquisición: {e}")
            await asyncio.sleep(5)