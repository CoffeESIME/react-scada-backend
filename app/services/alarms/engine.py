"""
Motor de Alarmas SCADA.
Monitorea valores de tags y genera alarmas cuando cruzan umbrales.
Implementa histéresis (deadband) para evitar "chattering" (activación-resolución rápida).
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Callable

from app.db.models import Tag, AlarmEvent, AlarmSeverity, AlarmStatus
from app.core.mqtt_client import mqtt_client

logger = logging.getLogger(__name__)

# Porcentaje de deadband por defecto sobre el rango del umbral.
# Ejemplo: si H=800 y deadband=0.02, la alarma se resuelve cuando valor <= 800 * (1-0.02) = 784
DEFAULT_DEADBAND_PERCENT = 0.02  # 2%


class AlarmEngine:
    """
    Motor de evaluación de alarmas con histéresis.

    La histéresis evita el "chattering": una alarma que se activa a H=800 no se
    resuelve hasta que el valor baja a H*(1-deadband). Esto previene el parpadeo
    rápido del indicador cuando el valor oscila alrededor del umbral.
    """

    def __init__(self, on_alarm_callback: Optional[Callable] = None):
        self.on_alarm_callback = on_alarm_callback
        self._tags: Dict[int, Tag] = {}
        # {alarm_key -> AlarmEvent} — alarmas activas en memoria
        self._active_alarms: Dict[str, AlarmEvent] = {}
        # {alarm_key -> severity_str} — severidad actual para saber si escalar/escalar
        self._active_severity: Dict[str, str] = {}

    def register_tag(self, tag: Tag) -> None:
        """Registra un tag para monitoreo de alarmas."""
        self._tags[tag.id] = tag

    async def evaluate(self, tag: Tag, value: float) -> Optional[AlarmEvent]:
        """
        Evalúa un valor contra los límites del tag con histéresis.

        Regla de histéresis:
          - Activación: value >= H  (cruce del umbral hacia arriba)
          - Resolución: value < H * (1 - deadband)  (debe bajar por debajo del deadband)

        Returns:
            AlarmEvent si se generó una nueva alarma, None si no.
        """
        if not tag.alarm_definition or not tag.alarm_definition.is_active:
            return None

        def_ = tag.alarm_definition
        limits = def_.limits or {}
        alarm_key = str(tag.id)

        # Leer umbrales configurados
        hh = limits.get("HH")
        ll = limits.get("LL")
        h  = limits.get("H")
        l  = limits.get("L")

        # Deadband configurable por tag (en el JSON de límites) o usar el default
        deadband = limits.get("deadband", DEFAULT_DEADBAND_PERCENT)

        # ── Determinar si el valor actual activa algún umbral ──────────────────
        severity = None
        message = ""

        if hh is not None and value >= hh:
            severity = AlarmSeverity.CRITICAL
            message = f"{def_.message} (HH: {value:.2f} >= {hh})"
        elif ll is not None and value <= ll:
            severity = AlarmSeverity.CRITICAL
            message = f"{def_.message} (LL: {value:.2f} <= {ll})"
        elif h is not None and value >= h:
            severity = AlarmSeverity.WARNING
            message = f"{def_.message} (H: {value:.2f} >= {h})"
        elif l is not None and value <= l:
            severity = AlarmSeverity.WARNING
            message = f"{def_.message} (L: {value:.2f} <= {l})"

        # ── Lógica de histéresis ───────────────────────────────────────────────
        is_currently_active = alarm_key in self._active_alarms

        if severity:
            # Hay condición de alarma — activar o mantener
            return await self._create_alarm(tag, value, severity, message)

        elif is_currently_active:
            # El valor no supera ningún umbral ahora.
            # Solo resolver si también supera la histéresis (ha bajado/subido lo suficiente).
            if self._is_within_deadband(value, limits, deadband):
                # Aún en la zona de histéresis — mantener alarma activa
                logger.debug(
                    f"[ALARM] Tag {tag.id} en deadband, alarma mantenida activa (value={value:.2f})"
                )
                return None
            else:
                # Salió de la zona de histéresis — resolver alarma
                await self._resolve_alarm(alarm_key)
                return None

        return None

    def _is_within_deadband(
        self, value: float, limits: dict, deadband: float
    ) -> bool:
        """
        Retorna True si el valor está dentro de la zona de histéresis
        (es decir, no ha bajado/subido lo suficiente del umbral como para
        considerar que la alarma se resolvió).
        """
        h  = limits.get("H")
        hh = limits.get("HH")
        l  = limits.get("L")
        ll = limits.get("LL")

        # Zona de histéresis para alarmas por arriba: [umbral * (1-deadband), umbral]
        if hh is not None and value >= hh * (1 - deadband):
            return True
        if h is not None and value >= h * (1 - deadband):
            return True

        # Zona de histéresis para alarmas por abajo: [umbral, umbral * (1+deadband)]
        if ll is not None and value <= ll * (1 + deadband):
            return True
        if l is not None and value <= l * (1 + deadband):
            return True

        return False

    async def _create_alarm(
        self, tag: Tag, value: float,
        severity: AlarmSeverity, message: str
    ) -> Optional[AlarmEvent]:
        """Crea y notifica una nueva alarma (sólo si no está ya activa)."""

        alarm_key = str(tag.id)

        if alarm_key not in self._active_alarms:
            alarm = AlarmEvent(
                definition_id=tag.alarm_definition.id,
                trigger_value=value,
                status=AlarmStatus.ACTIVE_UNACK,
                start_time=datetime.utcnow()
            )
            self._active_alarms[alarm_key] = alarm
            self._active_severity[alarm_key] = str(severity.value)

            await mqtt_client.publish_alarm(
                alarm_id=alarm_key,
                severity=str(severity.value),
                message=message,
                status="ACTIVE"
            )

            if self.on_alarm_callback:
                await self.on_alarm_callback(alarm)

            logger.warning(f"[ALARM] ACTIVA → Tag {tag.id}: {message}")
            return alarm

        # Alarma ya activa — no re-publicar para no saturar el bus MQTT
        return None

    async def _resolve_alarm(self, alarm_key: str) -> None:
        """Resuelve una alarma activa (Return To Normal)."""
        if alarm_key in self._active_alarms:
            alarm = self._active_alarms.pop(alarm_key)
            self._active_severity.pop(alarm_key, None)
            alarm.status = AlarmStatus.RESOLVED
            alarm.end_time = datetime.utcnow()

            await mqtt_client.publish_alarm(
                alarm_id=alarm_key,
                severity="INFO",
                message=f"Alarma resuelta (RTN): {alarm.trigger_value:.2f} → Normal",
                status="RESOLVED"   # <── cambiado de "NORMAL" a "RESOLVED"
            )

            logger.info(f"[ALARM] RESUELTA (RTN) → Tag {alarm_key}")


# Instancia global
alarm_engine = AlarmEngine()
