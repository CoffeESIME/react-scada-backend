"""
app/services/mqtt_listener.py — Punto Único de Ingesta de Datos del SCADA.

Tras la migración Edge-to-Cloud, este listener es EL único responsable
de recibir todos los datos de campo. El polling físico ya no existe en el backend.

Arquitectura:
  Edge Node (Modbus/OPC UA) → Broker MQTT → Este Listener → TimescaleDB + Alarms

Suscripciones:
  scada/tags/#   — Telemetría de tags publicada por los nodos Edge.
  scada/alarms/# — (futuro) Alarmas reportadas desde el Edge.

REGLA CRÍTICA DE TIEMPO:
  El timestamp de cada métrica guardada en TimescaleDB DEBE ser el que viene en el
  payload del Edge Node. El backend NO genera datetime.now() para datos de campo.
  Esto garantiza la fidelidad de los históricos contra deriva de reloj de red.

Formato de payload esperado desde el Edge:
  {
    "edge_id":   "edge_planta_norte_01",   // Identificador del nodo origen
    "tag_id":    14,                       // ID del tag en la BD central
    "tag_name":  "NIVEL_TK01",             // Nombre del tag
    "value":     78.5,                     // Valor medido
    "quality":   "GOOD",                   // Calidad: GOOD | BAD | UNCERTAIN
    "timestamp": "2026-05-23T20:50:43Z"   // Timestamp de la medición en el Edge
  }
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiomqtt
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.mqtt_client import mqtt_client, _build_tls_context
from app.db.session import async_session_factory
from app.db.models import Tag, ProtocolType
from app.services.storage import save_metric
from app.services.alarms.engine import alarm_engine

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Constantes de tópicos
# ──────────────────────────────────────────────────────────────────────────────
TOPIC_TAGS  = "scada/tags/#"
TOPIC_ALARMS = "scada/alarms/#"

# Mapa de caché: {tag_id: Tag} cargado desde BD para evitar consultas
# en cada mensaje. Se recarga cada CACHE_RELOAD_S segundos.
_tag_cache: Dict[int, Tag] = {}
_tag_name_cache: Dict[str, Tag] = {}  # Índice alternativo por nombre
CACHE_RELOAD_S = 60


# ──────────────────────────────────────────────────────────────────────────────
# Carga de caché de tags
# ──────────────────────────────────────────────────────────────────────────────

async def _load_tag_cache() -> None:
    """Carga todos los tags activos de la BD en memoria para lookups O(1)."""
    global _tag_cache, _tag_name_cache
    try:
        async with async_session_factory() as session:
            stmt = (
                select(Tag)
                .options(selectinload(Tag.alarm_definition))
                .where(Tag.is_enabled == True)
            )
            result = await session.execute(stmt)
            tags = result.scalars().all()

        _tag_cache = {t.id: t for t in tags}
        _tag_name_cache = {t.name: t for t in tags}
        logger.info("[LISTENER] Caché de tags cargada: %d tags activos.", len(tags))
    except Exception as exc:
        logger.error("[LISTENER] Error cargando caché de tags: %s", exc)


async def _periodic_cache_refresh() -> None:
    """Refresca la caché de tags periódicamente."""
    while True:
        await asyncio.sleep(CACHE_RELOAD_S)
        await _load_tag_cache()


# ──────────────────────────────────────────────────────────────────────────────
# Parser de timestamp (REGLA CRÍTICA)
# ──────────────────────────────────────────────────────────────────────────────

def _parse_edge_timestamp(timestamp_str: Optional[str], tag_name: str) -> datetime:
    """
    Parsea el timestamp enviado por el Edge Node.

    Acepta formatos ISO 8601:
      - "2026-05-23T20:50:43Z"
      - "2026-05-23T20:50:43.123456Z"
      - "2026-05-23T20:50:43+00:00"

    Si el timestamp es inválido o nulo, emite un WARNING y usa datetime.now(UTC)
    como fallback de emergencia — esto NO debe ocurrir en producción.
    """
    if not timestamp_str:
        logger.warning(
            "[LISTENER] Tag '%s': payload sin timestamp — usando now(UTC) como fallback.", tag_name
        )
        return datetime.now(timezone.utc)

    try:
        # Python 3.11+ acepta 'Z' directamente; para 3.10 lo reemplazamos.
        ts = timestamp_str.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(ts)
        # Asegurar que tenga tzinfo (ya sea UTC o lo que reportó el Edge).
        if parsed.tzinfo is None:
            logger.warning(
                "[LISTENER] Tag '%s': timestamp sin tzinfo '%s' — asumiendo UTC.",
                tag_name, timestamp_str,
            )
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError as exc:
        logger.warning(
            "[LISTENER] Tag '%s': timestamp inválido '%s' (%s) — usando now(UTC).",
            tag_name, timestamp_str, exc,
        )
        return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
# Procesamiento de mensajes de telemetría
# ──────────────────────────────────────────────────────────────────────────────

def _quality_to_opc_code(quality_str: str) -> int:
    """Convierte la calidad string del Edge a código numérico OPC UA."""
    mapping = {"GOOD": 192, "UNCERTAIN": 64, "BAD": 0}
    return mapping.get(quality_str.upper(), 0)


async def _process_tag_message(topic: str, payload_str: str) -> None:
    """
    Procesa un mensaje de telemetría entrante en el tópico scada/tags/*.

    Flujo:
      1. Parsear JSON del payload.
      2. Resolver el Tag desde la caché (por tag_id o tag_name).
      3. Extraer el timestamp del Edge (NUNCA generar uno propio).
      4. Guardar la métrica en TimescaleDB con ese timestamp.
      5. Pasar el valor al Alarm Engine para evaluación de umbrales.
    """
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        logger.error("[LISTENER] Payload no es JSON válido en tópico '%s': %s", topic, payload_str[:100])
        return

    # ── Resolución del Tag ────────────────────────────────────────────────────
    tag_id: Optional[int] = payload.get("tag_id")
    tag_name: str = payload.get("tag_name", "unknown")

    tag: Optional[Tag] = None
    if tag_id is not None:
        tag = _tag_cache.get(int(tag_id))
    if tag is None and tag_name != "unknown":
        tag = _tag_name_cache.get(tag_name)

    if tag is None:
        logger.warning(
            "[LISTENER] Tag no encontrado en caché (id=%s, name='%s'). "
            "¿Tag nuevo? La caché se refresca cada %ds.",
            tag_id, tag_name, CACHE_RELOAD_S,
        )
        return

    # ── Extracción de valor y calidad ────────────────────────────────────────
    raw_value = payload.get("value")
    if raw_value is None:
        logger.warning("[LISTENER] Payload sin 'value' para tag '%s'.", tag_name)
        return

    try:
        value = float(raw_value)
    except (ValueError, TypeError):
        logger.error("[LISTENER] Valor no numérico para tag '%s': %s", tag_name, raw_value)
        return

    quality_str: str = payload.get("quality", "GOOD")
    quality_code = _quality_to_opc_code(quality_str)

    # ── REGLA CRÍTICA: Extraer timestamp del Edge ────────────────────────────
    edge_timestamp = _parse_edge_timestamp(payload.get("timestamp"), tag_name)

    logger.debug(
        "[LISTENER] tag='%s' value=%.4f quality=%s ts=%s",
        tag_name, value, quality_str, edge_timestamp.isoformat(),
    )

    # ── Guardar en TimescaleDB con timestamp del Edge ────────────────────────
    saved = await save_metric(
        tag_id=tag.id,
        value=value,
        quality=quality_code,
        timestamp=edge_timestamp,   # ← Timestamp del reloj del Edge, NO del servidor.
    )
    if not saved:
        logger.error("[LISTENER] Fallo al guardar métrica para tag '%s'.", tag_name)

    # ── Evaluar alarmas ───────────────────────────────────────────────────────
    # Sólo evaluamos si la calidad es GOOD para no disparar falsas alarmas.
    if quality_str.upper() == "GOOD":
        try:
            await alarm_engine.evaluate(tag, value)
        except Exception as exc:
            logger.error("[LISTENER] Error en alarm_engine para tag '%s': %s", tag_name, exc)


# ──────────────────────────────────────────────────────────────────────────────
# Loop principal del Listener
# ──────────────────────────────────────────────────────────────────────────────

async def start_mqtt_listener() -> None:
    """
    Loop principal del Listener MQTT.

    Suscribe a scada/tags/# y procesa cada mensaje de telemetría entrante.
    Reconecta automáticamente ante desconexiones del broker.
    """
    logger.info("🚀 [LISTENER] Iniciando listener unificado de ingesta SCADA...")

    # Cargar caché inicial de tags.
    await _load_tag_cache()

    # Lanzar tarea de refresco periódico de caché.
    asyncio.create_task(_periodic_cache_refresh(), name="listener-cache-refresh")

    while True:
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_broker_host,
                port=settings.mqtt_broker_port,
                username=settings.mqtt_username,
                password=settings.mqtt_password,
                identifier=f"{settings.mqtt_client_id}-listener",
                tls_context=_build_tls_context(settings),
            ) as client:

                # Suscripciones: toda la telemetría de campo.
                await client.subscribe(TOPIC_TAGS)
                logger.info("[LISTENER] ✅ Suscrito a: %s", TOPIC_TAGS)

                await client.subscribe(TOPIC_ALARMS)
                logger.info("[LISTENER] ✅ Suscrito a: %s", TOPIC_ALARMS)

                # Bucle de recepción de mensajes.
                async for message in client.messages:
                    topic = str(message.topic)
                    payload_str = message.payload.decode("utf-8", errors="replace")

                    if topic.startswith("scada/tags/"):
                        # Lanzar el procesamiento como task para no bloquear el loop.
                        asyncio.create_task(
                            _process_tag_message(topic, payload_str),
                            name=f"process_{topic.split('/')[-1]}",
                        )
                    elif topic.startswith("scada/alarms/"):
                        # Placeholder para manejo futuro de alarmas reportadas por el Edge.
                        logger.debug("[LISTENER] Alarma recibida en %s: %s", topic, payload_str[:80])

        except aiomqtt.MqttError as exc:
            logger.error("[LISTENER] Error MQTT: %s — reconectando en 5s...", exc)
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("[LISTENER] Listener cancelado — saliendo limpiamente.")
            return
        except Exception as exc:
            logger.error("[LISTENER] Error inesperado: %s — reconectando en 5s...", exc)
            await asyncio.sleep(5)
