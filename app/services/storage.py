"""
Servicio para persistencia de métricas en TimescaleDB.

REGLA CRÍTICA DE TIEMPO:
  El backend NUNCA genera el timestamp de una métrica.
  El timestamp debe provenir siempre del dispositivo Edge que realizó la lectura.
  Esto garantiza que TimescaleDB registre el momento real de la medición en campo,
  no el momento en que el mensaje llegó al servidor (que puede incluir latencia de red).

  Si no se proporciona un timestamp externo (ej. en pruebas unitarias), se usa
  datetime.now(UTC) como fallback — esto debe evitarse en producción.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from app.db.session import async_session_factory
from app.db.models import Metric

logger = logging.getLogger(__name__)


async def save_metric(
    tag_id: int,
    value: float,
    quality: int = 192,
    timestamp: Optional[datetime] = None,
) -> bool:
    """
    Guarda una métrica en la hypertable de TimescaleDB.

    Args:
        tag_id:    ID del Tag en la base de datos.
        value:     Valor numérico de la medición.
        quality:   Código de calidad OPC UA (192 = Good, 0 = Bad).
        timestamp: Momento de la medición según el reloj del Edge Node.
                   Si es None, se usa datetime.now(UTC) como fallback de último recurso.
    """
    # Usar el timestamp del Edge si se proporcionó; fallback a UTC now.
    if timestamp is None:
        logger.warning(
            "[STORAGE] save_metric llamado sin timestamp para tag_id=%d — "
            "usando datetime.now(UTC) como fallback. Revisar origen del dato.", tag_id
        )
        timestamp = datetime.now(timezone.utc)

    try:
        async with async_session_factory() as session:
            metric = Metric(
                tag_id=tag_id,
                value=value,
                quality=quality,
                time=timestamp,
            )
            session.add(metric)
            await session.commit()
            return True

    except Exception as exc:
        logger.error("[STORAGE] Error guardando métrica tag_id=%d: %s", tag_id, exc)
        return False
