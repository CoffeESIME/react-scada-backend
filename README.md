<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue?style=for-the-badge&logo=python" alt="Python"/>
  <img src="https://img.shields.io/badge/FastAPI-0.128-009688?style=for-the-badge&logo=fastapi" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/TimescaleDB-PostgreSQL-336791?style=for-the-badge&logo=postgresql" alt="TimescaleDB"/>
  <img src="https://img.shields.io/badge/MQTT-Mosquitto-660066?style=for-the-badge&logo=eclipsemosquitto" alt="MQTT"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="MIT License"/>
</p>

<h1 align="center">⚙️ SCADA Backend</h1>

<p align="center">
  <strong>FastAPI + TimescaleDB backend for industrial data acquisition, tag management and SCADA screen persistence</strong>
</p>

<p align="center">
  <a href="#-overview">Overview</a> •
  <a href="#-screenshots">Screenshots</a> •
  <a href="#-api-reference">API Reference</a> •
  <a href="#-mqtt">MQTT</a> •
  <a href="#-protocols">Protocols</a> •
  <a href="#-installation">Installation</a> •
  <a href="#-build-your-own-frontend">Build Your Own Frontend</a>
</p>

---

## 📋 Overview

This is the **headless backend** of the React SCADA HMI system. It handles:

- **Data Acquisition** — Polls PLCs and IoT devices using multiple industrial protocols
- **Tag Management** — CRUD for sensor/actuator tags with per-tag alarm definitions
- **Real-time Publishing** — Broadcasts live values over MQTT for any frontend to consume
- **Historical Storage** — Persists time-series data in TimescaleDB
- **Screen Persistence** — Stores ReactFlow diagram layouts (nodes + edges) as JSON
- **Write Commands** — Accepts value writes and forwards them to MQTT for feedback

> 💡 **You can use this backend with any frontend.** Subscribe to the MQTT topics or query the REST API — no dependency on React or Next.js.

---

## 📸 Screenshots

> 💡 *Replace the placeholders below with actual screenshots of your deployment.*

### Swagger / Interactive API Docs
<!-- Screenshot: FastAPI /docs page showing all available endpoints grouped by router -->
![Swagger UI](docs/screenshots/swagger-ui.png)

### Tag Manager (via API)
<!-- Screenshot: GET /api/v1/tags response in a REST client showing tag list with protocols and alarm config -->
![Tag List API Response](docs/screenshots/tag-list-api.png)

### Real-time MQTT Output
<!-- Screenshot: MQTT client (e.g. MQTT Explorer) showing live tag values publishing on scada/tags/* topics -->
![MQTT Live Data](docs/screenshots/mqtt-live.png)

### TimescaleDB Historical Data
<!-- Screenshot: pgAdmin or psql showing the metrics hypertable with time-series rows -->
![TimescaleDB Metrics](docs/screenshots/timescaledb-metrics.png)

> 📁 Place screenshots in `docs/screenshots/` and commit them to the repo.

---

## 🔌 Supported Protocols

| Protocol | Status | Description |
|----------|--------|-------------|
| **Simulated** | ✅ Active | Signal generator (sine, ramp, random) — no hardware needed |
| **Modbus TCP** | ✅ Active | Read/write Modbus registers from PLCs |
| **OPC UA** | ✅ Active | OPC UA client — connects to industrial servers |
| **MQTT External** | ✅ Active | Subscribes to external topics (ESP32, IoT sensors) |

Each tag declares its own `source_protocol` and `connection_config`, so you can mix protocols within the same system.

---

## 🗺️ Architecture

```
                ┌───────────────────────────────────────┐
                │              FastAPI App               │
                │  /api/v1/tags  /api/v1/screens         │
                │  /api/v1/history  /auth                │
                └──────────────┬────────────────────────┘
                               │
          ┌────────────────────┼──────────────────────┐
          ▼                    ▼                       ▼
   ┌─────────────┐    ┌──────────────┐        ┌──────────────┐
   │ Acquisition │    │ TimescaleDB  │        │    MQTT      │
   │   Engine    │    │ (PostgreSQL) │        │   Broker     │
   │  (async     │───▶│  Tags        │        │  Mosquitto   │
   │   polling)  │    │  Metrics     │        │              │
   └──────┬──────┘    │  Screens     │        └──────┬───────┘
          │           │  Alarms      │               │
          │ publish   └──────────────┘   subscribe   │
          └──────────────────────────────────────────┘
                        scada/tags/{name}
```

---

## 📡 API Reference

**Base URL:** `http://localhost:8888`  
**Interactive docs:** `http://localhost:8888/docs`

---

### 🔖 Tags

Tags represent physical or virtual data points (sensors, actuators, signals).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/tags/` | List all tags (paginated, with filters) |
| `POST` | `/api/v1/tags/` | Create a new tag (optionally with alarm) |
| `GET` | `/api/v1/tags/{tag_id}` | Get tag detail including alarm definition |
| `PUT` | `/api/v1/tags/{tag_id}` | Update tag fields and/or alarm config |
| `DELETE` | `/api/v1/tags/{tag_id}` | Delete tag and its metric history |
| `POST` | `/api/v1/tags/{tag_id}/write` | Write a value to a tag (publishes to MQTT) |
| `DELETE` | `/api/v1/tags/{tag_id}/alarm` | Remove just the alarm definition for a tag |

#### Query Parameters — `GET /api/v1/tags/`

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | int | Page number (default: 1) |
| `page_size` | int | Results per page (default: 20, max: 100) |
| `protocol` | str | Filter by protocol: `simulated`, `modbus`, `opcua`, `mqtt` |
| `is_enabled` | bool | Filter by active/inactive tags |
| `search` | str | Partial name search (case-insensitive) |

#### Example — Create a Tag (with alarm)

```json
POST /api/v1/tags/
{
  "name": "Tank_Level_01",
  "description": "Main storage tank level",
  "unit": "%",
  "source_protocol": "simulated",
  "connection_config": {
    "signal_type": "sine",
    "min": 0,
    "max": 100
  },
  "scan_rate_ms": 1000,
  "mqtt_topic": "scada/tags/tank_level_01",
  "is_enabled": true,
  "alarm": {
    "high_high": 95,
    "high": 85,
    "low": 15,
    "low_low": 5
  }
}
```

#### Example — Write a value to a tag

```json
POST /api/v1/tags/1/write
{
  "value": 75.0
}
```

Response:
```json
{
  "status": "ok",
  "value": 75.0,
  "published_to": "scada/tags/tank_level_01"
}
```

---

### 🖥️ Screens

Screens store the full ReactFlow layout (nodes + edges JSON) for SCADA diagrams.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/screens/` | List all screens (lightweight, no layout_data) |
| `POST` | `/api/v1/screens/` | Create a new screen |
| `GET` | `/api/v1/screens/home` | Get the screen marked as home/default |
| `GET` | `/api/v1/screens/{slug_or_id}` | Get full screen by slug or numeric ID |
| `PUT` | `/api/v1/screens/{screen_id}` | Update screen layout or metadata |
| `DELETE` | `/api/v1/screens/{screen_id}` | Delete a screen |

#### Example — Create a screen

```json
POST /api/v1/screens/
{
  "name": "Tank Farm Overview",
  "description": "Main overview of the tank farm area",
  "is_home": true,
  "layout_data": {
    "nodes": [...],
    "edges": [...]
  }
}
```

> The `slug` is auto-generated from the name (`"Tank Farm Overview"` → `"tank-farm-overview"`) if not provided.

---

### 📈 History

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/history` | Get historical data for multiple tags in a time range |
| `GET` | `/api/v1/history/latest/{tag_id}` | Get the latest N records for a tag |

#### Query Parameters — `GET /api/v1/history`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tag_ids` | str | ✅ | Comma-separated tag IDs, e.g. `"1,2,3"` |
| `start` | ISO 8601 | ✅ | Start of time range |
| `end` | ISO 8601 | ✅ | End of time range |

#### Example response

```json
[
  {
    "tagId": 1,
    "tagName": "Tank_Level_01",
    "data": [
      { "x": "2026-03-04T10:00:00", "y": 67.4 },
      { "x": "2026-03-04T10:00:01", "y": 68.1 }
    ]
  }
]
```

---

### 🔐 Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/register` | Register a new user |
| `POST` | `/auth/jwt/login` | Login — returns JWT token |
| `POST` | `/auth/jwt/logout` | Logout |
| `GET` | `/users/me` | Get current user profile |

Uses [fastapi-users](https://fastapi-users.github.io/fastapi-users/) with JWT Bearer tokens.

---

### 🩺 System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | System status |
| `GET` | `/health` | Health check |
| `GET` | `/api/v1/health` | API health check |

---

## 📡 MQTT Communication

**Broker:** Mosquitto on `localhost:1883` (internal) / `localhost:9001` (WebSocket for browsers)

### Topics published by the backend

| Topic | Payload | Description |
|-------|---------|-------------|
| `scada/tags/{tag_name}` | `{ tag_id, tag_name, value, timestamp, quality }` | Live tag value from acquisition engine |
| `scada/alarms/{severity}` | `{ tag_id, message, threshold, value }` | Alarm notification |

### Topics subscribed by the backend

| Topic | Purpose |
|-------|---------|
| Configurable per tag in `connection_config.topic` | Receives values from external MQTT devices (ESP32, etc.) |

#### Example MQTT payload

```json
{
  "tag_id": 1,
  "tag_name": "Tank_Level_01",
  "value": 67.4,
  "timestamp": "2026-03-04T16:00:00.000Z",
  "quality": "GOOD"
}
```

`quality` can be `"GOOD"`, `"BAD"`, or `"MANUAL_WRITE"`.

---

## 📁 Project Structure

```
scada-backend/
├── app/
│   ├── api/
│   │   ├── auth.py          # Authentication routes
│   │   ├── tags.py          # Tags + Alarms CRUD
│   │   ├── screens.py       # Screens CRUD (ReactFlow layouts)
│   │   ├── history.py       # Time-series queries
│   │   └── endpoints.py     # Health check routes
│   ├── core/
│   │   ├── config.py        # Pydantic Settings (env vars)
│   │   └── mqtt_client.py   # Global MQTT client
│   ├── db/
│   │   ├── models.py        # SQLModel models (Tag, Metric, Screen, Alarm)
│   │   └── session.py       # Async PostgreSQL engine
│   ├── schemas/             # Pydantic request/response schemas
│   ├── services/
│   │   ├── bridges/         # Protocol drivers (Factory Pattern)
│   │   │   ├── base.py
│   │   │   ├── factory.py
│   │   │   ├── modbus.py
│   │   │   ├── opcua.py
│   │   │   └── simulator.py
│   │   ├── engine.py        # Acquisition loop (async polling)
│   │   ├── history.py       # Historical query logic
│   │   ├── mqtt_listener.py # External MQTT device listener
│   │   └── storage.py       # Metric persistence
│   ├── users.py             # fastapi-users config
│   └── main.py              # FastAPI app entry point
├── scripts/
│   └── seed_data.py         # Sample tag seeding script
├── .env                     # Environment variables (not committed)
├── pyproject.toml           # Dependencies (Poetry)
└── README.md
```

---

## ⚙️ Installation

### Prerequisites

- **Python 3.12+**
- **Poetry**
- **TimescaleDB** (or plain PostgreSQL) on `localhost:5470`
- **Mosquitto** on `localhost:1883`

> 💡 Infrastructure (TimescaleDB, Mosquitto, pgAdmin) is managed in the companion `scada` docker-compose repository.

### 1. Install dependencies

```bash
cd scada-backend
poetry install
```

### 2. Configure environment

```env
# .env
POSTGRES_HOST=localhost
POSTGRES_PORT=5470
POSTGRES_USER=admin
POSTGRES_PASSWORD=your_password
POSTGRES_DB=scada_system

MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
```

### 3. Start the server

```bash
poetry run uvicorn app.main:app --host 127.0.0.1 --port 8888 --reload
```

### 4. Seed sample data

```bash
poetry run python scripts/seed_data.py
```

### 5. Open interactive API docs

```
http://localhost:8888/docs
```

---

## 🏗️ Build Your Own Frontend

This backend is **frontend-agnostic**. You can build your own HMI with any framework (Vue, Angular, Svelte, plain HTML, native mobile, etc.) by:

1. **Subscribing to MQTT** over WebSocket (`ws://host:9001`) to receive live tag values  
2. **Querying the REST API** for configuration, history and screen layouts  
3. **POSTing to `/write`** to send control commands  

### Minimal integration example (JavaScript)

```js
import mqtt from 'mqtt';
import axios from 'axios';

const API = 'http://localhost:8888/api/v1';
const client = mqtt.connect('ws://localhost:9001');

// 1. Fetch all tags
const { data } = await axios.get(`${API}/tags/`);

// 2. Subscribe to live updates
client.subscribe('scada/tags/#');
client.on('message', (topic, message) => {
  const payload = JSON.parse(message.toString());
  console.log(`${payload.tag_name} = ${payload.value} @ ${payload.timestamp}`);
});

// 3. Write a value
await axios.post(`${API}/tags/1/write`, { value: 80.0 });

// 4. Load a SCADA screen layout
const screen = await axios.get(`${API}/screens/tank-farm-overview`);
// screen.data.layout_data contains { nodes, edges } — ready for ReactFlow or your own renderer
```

---

## 🗺️ Roadmap

- [ ] Motor de alarmas con evaluación en tiempo real (HH / H / L / LL)
- [ ] Endpoint de histórico de alarmas
- [ ] WebSocket nativo para streaming sin MQTT
- [ ] Escritura real en Modbus / OPC UA (actualmente simulated mode publica en MQTT)
- [ ] Soporte para protocolo BACnet
- [ ] Docker image publicada en Docker Hub

---

## 📄 License

MIT © 2026 Fabian — see [LICENSE](LICENSE)

## 👤 Author

**Fabian** — [heromfabian@gmail.com](mailto:heromfabian@gmail.com)
