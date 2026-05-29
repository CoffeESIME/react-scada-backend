"""
API de Alarmas Activas.

Expone el estado en memoria del AlarmEngine para que el frontend pueda
hacer un bootstrap al montar (mismo patrón que getLatestHistory en DataTrend).

Endpoints:
  GET /api/alarms/active  → Lista de alarmas actualmente activas en memoria.
"""
import logging
from fastapi import APIRouter, Depends

from app.db.models import User
from app.users import current_active_user
from app.services.alarms.engine import alarm_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alarms", tags=["alarms"])


@router.get("/active")
async def get_active_alarms(
    user: User = Depends(current_active_user),
):
    """
    Devuelve todas las alarmas actualmente activas en el motor de alarmas.

    El frontend lo usa al montar para sincronizar el alarmStore con el estado
    real del sistema, evitando que los indicadores de alarma aparezcan como
    'normal' cuando en realidad hay una alarma activa que se disparó mientras
    el usuario no estaba en la pantalla de runtime.

    Respuesta:
    [
      {
        "alarm_id": "14",          // == tag_id (clave del motor)
        "tag_id": 14,
        "severity": "WARNING",     // CRITICAL | WARNING
        "message": "Nivel alto (H: 85.20 >= 80)",
        "status": "ACTIVE",
        "trigger_value": 85.20
      },
      ...
    ]
    """
    active = []

    for alarm_key, alarm_event in alarm_engine._active_alarms.items():
        severity_str = alarm_engine._active_severity.get(alarm_key, "WARNING")
        active.append({
            "alarm_id":      alarm_key,
            "tag_id":        int(alarm_key),
            "severity":      severity_str,
            "message":       f"Alarma activa (valor disparador: {alarm_event.trigger_value:.2f})",
            "status":        "ACTIVE",
            "trigger_value": alarm_event.trigger_value,
            "start_time":    alarm_event.start_time.isoformat() if alarm_event.start_time else None,
        })

    logger.debug("[ALARMS] Bootstrap request: %d alarmas activas devueltas.", len(active))
    return active
