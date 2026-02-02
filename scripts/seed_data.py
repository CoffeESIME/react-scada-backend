import asyncio
import sys
import os

# Asegurar que el directorio raíz está en el path para importar app
sys.path.append(os.getcwd())

from sqlmodel import select
from app.db.session import async_session_factory
from app.db.models import Tag, ProtocolType

async def init_db_data():
    async with async_session_factory() as session:
        print("🌱 Iniciando sembrado inteligente de datos...")
        
        # Definimos la lista completa de Tags que QUEREMOS tener
        tags_definitions = [
            # --- GRUPO 1: BÁSICOS ---
            {
                "name": "Demo_Sinewave",
                "description": "Generador de onda senoidal virtual",
                "unit": "Amps",
                "source_protocol": ProtocolType.SIMULATED,
                "connection_config": {"signal_type": "sine", "min": 0, "max": 100},
                "scan_rate_ms": 1000,
                "mqtt_topic": "scada/tags/demo_sinewave",
                "is_enabled": True
            },
            {
                "name": "Tanque_Principal_Nivel",
                "description": "Nivel simulado del tanque principal",
                "unit": "Liters",
                "source_protocol": ProtocolType.SIMULATED,
                "connection_config": {"signal_type": "random", "min": 40, "max": 60},
                "scan_rate_ms": 2000,
                "mqtt_topic": "scada/tags/tanque_main",
                "is_enabled": True
            },
            {
                "name": "Sensor_Temperatura_Patio",
                "description": "Lectura remota vía MQTT",
                "unit": "°C",
                "source_protocol": ProtocolType.MQTT, 
                "connection_config": {"topic": "device/esp32_01/temp", "json_key": "val"},
                "scan_rate_ms": 0,
                "mqtt_topic": "scada/tags/temp_patio",
                "is_enabled": True
            },
            # --- GRUPO 2: LAZO PID ---
            {
                "name": "PID_Horno_PV",
                "description": "Temperatura Actual del Horno",
                "unit": "°C",
                "source_protocol": ProtocolType.SIMULATED,
                "connection_config": {"signal_type": "sine", "min": 180, "max": 220, "period": 60}, 
                "scan_rate_ms": 1000,
                "mqtt_topic": "scada/tags/pid_horno_pv",
                "is_enabled": True
            },
            {
                "name": "PID_Horno_SP",
                "description": "Setpoint Temperatura Horno",
                "unit": "°C",
                "source_protocol": ProtocolType.SIMULATED,
                "connection_config": {"signal_type": "random", "min": 199, "max": 201}, 
                "scan_rate_ms": 2000,
                "mqtt_topic": "scada/tags/pid_horno_sp",
                "is_enabled": True
            },
            {
                "name": "PID_Horno_Out",
                "description": "Apertura Válvula Gas",
                "unit": "%",
                "source_protocol": ProtocolType.SIMULATED,
                "connection_config": {"signal_type": "sine", "min": 40, "max": 60}, 
                "scan_rate_ms": 1000,
                "mqtt_topic": "scada/tags/pid_horno_out",
                "is_enabled": True
            },
            {
                "name": "PID_Horno_Mode",
                "description": "Estado Lazo PID (0=Man, 1=Auto)",
                "unit": "",
                "source_protocol": ProtocolType.SIMULATED,
                "connection_config": {"signal_type": "random", "min": 0, "max": 1},
                "scan_rate_ms": 5000,
                "mqtt_topic": "scada/tags/pid_horno_mode",
                "is_enabled": True
            },
            # --- GRUPO 3: DISCRETOS ---
            {
                "name": "Bomba_Agua_Status",
                "description": "Estado de marcha bomba alimentación",
                "unit": "Sts",
                "source_protocol": ProtocolType.SIMULATED,
                "connection_config": {"signal_type": "random", "min": 0, "max": 1},
                "scan_rate_ms": 3000,
                "mqtt_topic": "scada/tags/bomba_status",
                "is_enabled": True
            }
        ]

        created_count = 0
        
        # Iteramos sobre la lista y verificamos uno por uno
        for tag_data in tags_definitions:
            # Buscamos si ya existe un tag con ese NOMBRE exacto
            query = select(Tag).where(Tag.name == tag_data["name"])
            result = await session.execute(query)
            existing_tag = result.scalar_one_or_none()

            if existing_tag:
                print(f"   ⚠️  Saltando {tag_data['name']} (Ya existe con ID: {existing_tag.id})")
            else:
                # Si no existe, lo creamos
                new_tag = Tag(**tag_data)
                session.add(new_tag)
                print(f"   ✅ Creando {tag_data['name']}...")
                created_count += 1
        
        await session.commit()
        
        if created_count > 0:
            print(f"\n✨ Se agregaron {created_count} nuevos tags a la base de datos.")
        else:
            print("\n👌 Todos los tags ya existían. No se agregaron nuevos.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(init_db_data())