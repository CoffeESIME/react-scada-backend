# SCADA Backend

![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/TimescaleDB-PostgreSQL-336791?logo=postgresql)
![MQTT](https://img.shields.io/badge/MQTT-Mosquitto-660066?logo=eclipsemosquitto)

Backend del sistema SCADA IIoT para monitoreo y control industrial. Proporciona una API REST para la gestión de tags, métricas históricas y alarmas, con soporte para múltiples protocolos industriales.

---

## 🚀 Características Actuales

### Protocolos Soportados
| Protocolo | Estado | Descripción |
|-----------|--------|-------------|
| **Simulado** | ✅ Implementado | Generador de señales (seno, rampa, aleatorio) para pruebas |
| **Modbus TCP** | ✅ Implementado | Lectura/escritura de registros Modbus |
| **OPC UA** | ✅ Implementado | Cliente OPC UA para conexión a servidores industriales |
| **MQTT Externo** | ✅ Implementado | Listener para dispositivos IoT (ESP32, sensores) |

### Servicios
- **Motor de Adquisición de Datos**: Loop de polling configurable por tag
- **Listener MQTT**: Suscripción a topics externos y normalización de datos
- **Almacenamiento en TimescaleDB**: Persistencia de métricas con soporte para series temporales
- **API REST**: Endpoints para consulta de tags y métricas

---

## 📁 Estructura del Proyecto

```
scada-backend/
├── app/
│   ├── api/              # Endpoints REST
│   │   └── endpoints.py  # Rutas /api/v1/*
│   ├── core/             # Configuración global
│   │   ├── config.py     # Variables de entorno (Pydantic Settings)
│   │   └── mqtt_client.py
│   ├── db/               # Capa de datos
│   │   ├── models.py     # Modelos SQLModel (Tag, Metric, Screen, Alarm)
│   │   └── session.py    # Engine async PostgreSQL
│   ├── services/         # Lógica de negocio
│   │   ├── bridges/      # Drivers de protocolo (Factory Pattern)
│   │   │   ├── base.py
│   │   │   ├── factory.py
│   │   │   ├── modbus.py
│   │   │   ├── opcua.py
│   │   │   └── simulator.py
│   │   ├── engine.py     # Motor de adquisición
│   │   ├── mqtt_listener.py
│   │   └── storage.py    # Persistencia de métricas
│   └── main.py           # Punto de entrada FastAPI
├── scripts/
│   └── seed_data.py      # Datos de prueba
├── .env                  # Variables de entorno
├── pyproject.toml        # Dependencias (Poetry)
└── README.md
```

---

## ⚙️ Requisitos Previos

- **Python 3.12+**
- **Poetry** (gestor de dependencias)
- **TimescaleDB** o PostgreSQL (corriendo en localhost:5470)
- **Mosquitto** (broker MQTT, corriendo en localhost:1883)

> 💡 La infraestructura (TimescaleDB, Mosquitto, PgAdmin) se gestiona en un repositorio separado con Docker Compose.

---

## 🛠️ Instalación y Ejecución Local

### 1. Clonar e instalar dependencias

```bash
cd scada-backend
poetry install
```

### 2. Configurar variables de entorno

Edita el archivo `.env` según tu configuración local:

```env
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5470
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin_scada_secret
POSTGRES_DB=scada_system

# MQTT
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
```

### 3. Iniciar la aplicación

```bash
poetry run uvicorn app.main:app --host 127.0.0.1 --port 8888 --reload
```

### 4. Sembrar datos de prueba

```bash
poetry run python scripts/seed_data.py
```

---

## 📡 Endpoints API

Base URL: `http://localhost:8888`

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/` | Estado del sistema |
| `GET` | `/health` | Health check |
| `GET` | `/api/v1/health` | Health check del servicio |
| `GET` | `/api/v1/tags` | Lista todos los tags registrados |
| `GET` | `/api/v1/tags/{tag_id}` | Obtiene un tag específico (TODO) |
| `GET` | `/api/v1/metrics/{tag_id}` | Obtiene métricas históricas (TODO) |

### Ejemplo de respuesta `/api/v1/tags`

```json
{
  "tags": [
    {
      "id": 1,
      "name": "Demo_Sinewave",
      "description": "Generador de onda senoidal virtual",
      "unit": "Amps",
      "source_protocol": "simulated",
      "connection_config": {"signal_type": "sine", "min": 0, "max": 100},
      "scan_rate_ms": 1000,
      "mqtt_topic": "scada/tags/demo_sinewave",
      "is_enabled": true
    }
  ]
}
```

---

## 🔌 Comunicación MQTT

### Topics Internos (Publicados por el Backend)
- `scada/tags/{tag_name}` - Valores normalizados de cada tag
- `scada/alarms/{severity}` - Notificaciones de alarmas

### Topics Externos (Escuchados por el Backend)
- Configurables por tag en `connection_config.topic`
- Ejemplo: `device/esp32_01/temp`

---

## 🗺️ Roadmap - Próximas Mejoras

### Corto Plazo
- [ ] Implementar endpoint `GET /api/v1/tags/{id}` completo
- [ ] Implementar endpoint `GET /api/v1/metrics/{id}` con agregaciones de TimescaleDB
- [ ] Agregar endpoint `POST /api/v1/tags` para crear tags desde la API
- [ ] Sistema de autenticación con FastAPI-Users (JWT)

### Mediano Plazo
- [ ] Motor de alarmas con evaluación de umbrales (HH, H, L, LL)
- [ ] Endpoint para histórico de alarmas
- [ ] WebSocket para streaming de datos en tiempo real
- [ ] CRUD completo de pantallas/layouts (React Flow export)

### Largo Plazo
- [ ] Soporte para escritura en PLCs (Modbus write, OPC UA write)
- [ ] Dashboard de administración
- [ ] Integración con sistema de audio/TTS para alarmas críticas
- [ ] Soporte para protocolo BACnet

---

## 🧪 Testing

```bash
# Ejecutar tests (cuando estén implementados)
poetry run pytest
```

---

## 📄 Licencia

Este proyecto es parte de un sistema SCADA educativo/demostrativo.

---

## 👤 Autor

**Fabian** - [heromfabian@gmail.com](mailto:heromfabian@gmail.com)
