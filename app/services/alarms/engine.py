"""
Motor de Alarmas SCADA.
Monitorea valores de tags y genera alarmas cuando cruzan umbrales.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Callable

from app.db.models import Tag, AlarmEvent, AlarmSeverity, AlarmStatus
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
        self._active_alarms: Dict[str, AlarmEvent] = {}
    
    def register_tag(self, tag: Tag) -> None:
        """Registra un tag para monitoreo de alarmas."""
        self._tags[tag.id] = tag
    
    async def evaluate(self, tag: Tag, value: float) -> Optional[AlarmEvent]:
        """
        Evalúa un valor contra los límites del tag.
        
        Returns:
            AlarmEvent si se generó una nueva alarma, None si no.
        """
        if not tag.alarm_definition or not tag.alarm_definition.is_active:
            return None
            
        def_ = tag.alarm_definition
        limits = def_.limits or {}
        
        alarm = None
        alarm_key = f"{tag.id}"
        
        # Evaluar límites (de más crítico a menos)
        hh = limits.get("HH")
        ll = limits.get("LL")
        h = limits.get("H")
        l = limits.get("L")
        
        message = ""
        severity = None
        
        if hh is not None and value >= hh:
            severity = AlarmSeverity.CRITICAL
            message = f"{def_.message} (HH: {value} >= {hh})"
        elif ll is not None and value <= ll:
            severity = AlarmSeverity.CRITICAL
            message = f"{def_.message} (LL: {value} <= {ll})"
        elif h is not None and value >= h:
            severity = AlarmSeverity.WARNING
            message = f"{def_.message} (H: {value} >= {h})"
        elif l is not None and value <= l:
            severity = AlarmSeverity.WARNING
            message = f"{def_.message} (L: {value} <= {l})"
        else:
            # Valor normal - resolver alarma activa si existe
            if alarm_key in self._active_alarms:
                await self._resolve_alarm(alarm_key)
            return None
            
        if severity:
            alarm = await self._create_alarm(
                tag, value, severity, message
            )

        return alarm
    
    async def _create_alarm(
        self, tag: Tag, value: float, 
        severity: AlarmSeverity, message: str
    ) -> AlarmEvent:
        """Crea y notifica una nueva alarma."""
        # TODO: Persistir en BD usando una sesión si es necesario
        
        alarm = AlarmEvent(
            definition_id=tag.alarm_definition.id,
            trigger_value=value,
            status=AlarmStatus.ACTIVE_UNACK,
            start_time=datetime.utcnow()
        )
        
        alarm_key = f"{tag.id}"
        
        if alarm_key not in self._active_alarms:
             self._active_alarms[alarm_key] = alarm
             
             # Publicar por MQTT
             await mqtt_client.publish_alarm(
                alarm_id=alarm_key,
                severity=str(severity.value), # Int as str
                message=message,
                status="ACTIVE"
             )
             
             # Callback externo
             if self.on_alarm_callback:
                await self.on_alarm_callback(alarm)
             
             logger.warning(f"Alarm triggered: {message}")
             return alarm
        
        return None
    
    async def _resolve_alarm(self, alarm_key: str) -> None:
        """Resuelve una alarma activa."""
        if alarm_key in self._active_alarms:
            alarm = self._active_alarms.pop(alarm_key)
            alarm.status = AlarmStatus.RESOLVED # Database status can remain RESOLVED or CLEARED
            alarm.end_time = datetime.utcnow()
            
            # Notificar resolución (Return to Normal)
            await mqtt_client.publish_alarm(
                alarm_id=alarm_key,
                severity="INFO", 
                message=f"Alarm resolved: {alarm.trigger_value} -> Normal",
                status="NORMAL" 
            )
            
            logger.info(f"Alarm resolved (RTN) for tag {alarm_key}")


# Instancia global
alarm_engine = AlarmEngine()
