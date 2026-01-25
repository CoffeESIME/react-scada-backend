"""
Motor de Alarmas SCADA.
Monitorea valores de tags y genera alarmas cuando cruzan umbrales.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Callable

from app.db.models import Tag, Alarm, AlarmSeverity, AlarmStatus
from app.core.mqtt_client import mqtt_client

logger = logging.getLogger(__name__)


class AlarmEngine:
    """
    Motor de evaluación de alarmas.
    Compara valores en tiempo real contra límites configurados.
    """
    
    def __init__(self, on_alarm_callback: Optional[Callable] = None):
        self.on_alarm_callback = on_alarm_callback
        self._tags: Dict[int, Tag] = {}
        self._active_alarms: Dict[str, Alarm] = {}
    
    def register_tag(self, tag: Tag) -> None:
        """Registra un tag para monitoreo de alarmas."""
        self._tags[tag.id] = tag
    
    async def evaluate(self, tag_id: int, value: float) -> Optional[Alarm]:
        """
        Evalúa un valor contra los límites del tag.
        
        Returns:
            Alarm si se generó una nueva alarma, None si no.
        """
        tag = self._tags.get(tag_id)
        if not tag:
            return None
        
        alarm = None
        alarm_key = f"{tag_id}"
        
        # Evaluar límites (de más crítico a menos)
        if tag.high_high_limit and value >= tag.high_high_limit:
            alarm = await self._create_alarm(
                tag, value, AlarmSeverity.CRITICAL,
                f"{tag.name} muy alto: {value} >= {tag.high_high_limit}"
            )
        elif tag.low_low_limit and value <= tag.low_low_limit:
            alarm = await self._create_alarm(
                tag, value, AlarmSeverity.CRITICAL,
                f"{tag.name} muy bajo: {value} <= {tag.low_low_limit}"
            )
        elif tag.high_limit and value >= tag.high_limit:
            alarm = await self._create_alarm(
                tag, value, AlarmSeverity.WARNING,
                f"{tag.name} alto: {value} >= {tag.high_limit}"
            )
        elif tag.low_limit and value <= tag.low_limit:
            alarm = await self._create_alarm(
                tag, value, AlarmSeverity.WARNING,
                f"{tag.name} bajo: {value} <= {tag.low_limit}"
            )
        else:
            # Valor normal - resolver alarma activa si existe
            if alarm_key in self._active_alarms:
                await self._resolve_alarm(alarm_key)
        
        return alarm
    
    async def _create_alarm(
        self, tag: Tag, value: float, 
        severity: AlarmSeverity, message: str
    ) -> Alarm:
        """Crea y notifica una nueva alarma."""
        alarm = Alarm(
            tag_id=tag.id,
            severity=severity,
            status=AlarmStatus.ACTIVE,
            message=message,
            triggered_value=value,
            triggered_at=datetime.utcnow()
        )
        
        alarm_key = f"{tag.id}"
        self._active_alarms[alarm_key] = alarm
        
        # Publicar por MQTT
        await mqtt_client.publish_alarm(
            alarm_id=alarm_key,
            severity=severity.value,
            message=message
        )
        
        # Callback externo
        if self.on_alarm_callback:
            await self.on_alarm_callback(alarm)
        
        logger.warning(f"Alarm triggered: {message}")
        return alarm
    
    async def _resolve_alarm(self, alarm_key: str) -> None:
        """Resuelve una alarma activa."""
        if alarm_key in self._active_alarms:
            alarm = self._active_alarms.pop(alarm_key)
            alarm.status = AlarmStatus.RESOLVED
            alarm.resolved_at = datetime.utcnow()
            logger.info(f"Alarm resolved: {alarm.message}")


# Instancia global
alarm_engine = AlarmEngine()
