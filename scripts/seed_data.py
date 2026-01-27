import asyncio
import sys
import os

# Asegurar que el directorio raíz está en el path para importar app
sys.path.append(os.getcwd())

from sqlmodel import select
from app.db.session import async_session_factory
from app.db.models import Tag, ProtocolType, User

async def init_db_data():
    async with async_session_factory() as session:
        # 1. Verificar si ya existen Tags
        result = await session.execute(select(Tag))
        existing_tag = result.scalars().first()
        
        if not existing_tag:
            print("🌱 Base de datos vacía. Sembrando datos de demo...")
            
            # Tag Simulado 1: Onda Senoidal (Para ver gráficas bonitas)
            demo_tag_1 = Tag(
                name="Demo_Sinewave",
                description="Generador de onda senoidal virtual",
                unit="Amps",
                source_protocol=ProtocolType.SIMULATED,
                connection_config={"signal_type": "sine", "min": 0, "max": 100},
                scan_rate_ms=1000,
                mqtt_topic="scada/tags/demo_sinewave",
                is_enabled=True
            )
            
            # Tag Simulado 2: Tanque Aleatorio (Para probar alarmas)
            demo_tag_2 = Tag(
                name="Tanque_Principal_Nivel",
                description="Nivel simulado del tanque principal",
                unit="Liters",
                source_protocol=ProtocolType.SIMULATED,
                connection_config={"signal_type": "random", "min": 40, "max": 60},
                scan_rate_ms=2000,
                mqtt_topic="scada/tags/tanque_main",
                is_enabled=True
            )

            # Tag MQTT Externo (Para probar tu ESP32 imaginario)
            demo_tag_3 = Tag(
                name="Sensor_Temperatura_Patio",
                description="Lectura remota vía MQTT",
                unit="°C",
                source_protocol=ProtocolType.MQTT, 
                connection_config={"topic": "device/esp32_01/temp", "json_key": "val"},
                scan_rate_ms=0, # No se escanea
                mqtt_topic="scada/tags/temp_patio",
                is_enabled=True
            )

            session.add(demo_tag_1)
            session.add(demo_tag_2)
            session.add(demo_tag_3)
            
            await session.commit()
            print("✅ Datos semilla creados exitosamente.")
        else:
            print("👌 La base de datos ya tiene datos.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(init_db_data())
