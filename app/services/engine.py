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

async def data_acquisition_loop():
    """
    Motor de Polling (Solicitud Activa).
    SOLO procesa protocolos que requieren interrogación: Modbus, OPC UA, Simulación.
    IGNORA protocolos pasivos como MQTT (esos los maneja el mqtt_listener).
    """
    # logger.info("🚀 Iniciando Motor de Polling (Modbus/OPCUA/Sim)...")  # Comentado
    print("🚀 [ENGINE] Motor de Polling iniciado (logs reducidos para debug MQTT)")
    
    while True:
        try:
            async with async_session_factory() as session:
                # 1. FILTRADO INTELIGENTE
                # Solo traemos tags habilitados Y que NO sean MQTT
                stmt = select(Tag).options(selectinload(Tag.alarm_definition)).where(
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
                        # Fallback: si no tiene mqtt_topic, usar el nombre del tag
                        topic = tag.mqtt_topic or f"scada/tags/{tag.name}"
                        
                        # Debug: mostrar qué se publica
                        print(f"📤 [ENGINE] Publicando: topic={topic}, value={raw_value}, tag_id={tag.id}")
                        
                        # Publicamos (Fire and forget)
                        await mqtt_client.publish(topic, json.dumps(payload_dict), qos=0)
                        
                        # 5. Guardar en TimescaleDB para historial
                        from app.services.storage import save_metric
                        await save_metric(tag_id=tag.id, value=raw_value)
                        
                        # 6. Evaluar Alarmas
                        await alarm_engine.evaluate(tag, raw_value)
                            
                except Exception as e:
                    print(f"⚠️ [ENGINE] Error leyendo tag {tag.name}: {e}")

            # Scan Rate Global (Simplificado para MVP)
            # En producción, cada tag debería tener su propio timer.
            await asyncio.sleep(1)

        except Exception as e:
            # logger.error(f"🔥 Error crítico en loop de adquisición: {e}")  # Comentado
            print(f"🔥 [ENGINE] Error crítico: {e}")
            await asyncio.sleep(5)