"""
Cliente MQTT interno para publicar alertas y comandos.
Usa aiomqtt para operaciones asíncronas.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

import aiomqtt

from app.core.config import settings

logger = logging.getLogger(__name__)


class MQTTClient:
    """Cliente MQTT singleton para el backend."""
    
    _instance: Optional["MQTTClient"] = None
    _client: Optional[aiomqtt.Client] = None
    _connected: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @asynccontextmanager
    async def get_client(self):
        """Context manager para obtener el cliente MQTT."""
        async with aiomqtt.Client(
            hostname=settings.mqtt_broker_host,
            port=settings.mqtt_broker_port,
            username=settings.mqtt_username,
            password=settings.mqtt_password,
            identifier=settings.mqtt_client_id,
        ) as client:
            yield client
    
    async def publish(self, topic: str, payload: str, qos: int = 1) -> bool:
        """
        Publica un mensaje en un topic MQTT.
        
        Args:
            topic: Topic de destino (ej: "scada/alarms/motor_01")
            payload: Contenido del mensaje (generalmente JSON)
            qos: Quality of Service (0, 1, o 2)
        
        Returns:
            True si se publicó correctamente
        """
        try:
            async with self.get_client() as client:
                await client.publish(topic, payload, qos=qos)
                logger.info(f"Published to {topic}: {payload[:50]}...")
                return True
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            return False
    
    async def publish_alarm(self, alarm_id: str, severity: str, message: str, status: str = "ACTIVE") -> bool:
        """
        Publica una alarma en el topic de alarmas.
        
        Args:
            alarm_id: Identificador único de la alarma
            severity: Nivel de severidad (info, warning, critical)
            message: Descripción de la alarma
            status: Estado (ACTIVE, RESOLVED)
        """
        import json
        from datetime import datetime
        
        payload = json.dumps({
            "alarm_id": alarm_id,
            "severity": severity,
            "message": message,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        topic = f"scada/alarms/{severity}"
        return await self.publish(topic, payload)
    
    async def send_command(self, device_id: str, command: str, value: any) -> bool:
        """
        Envía un comando a un dispositivo ESP32.
        
        Args:
            device_id: ID del dispositivo destino
            command: Tipo de comando (ej: "set_state", "set_value")
            value: Valor del comando
        """
        import json
        
        payload = json.dumps({
            "command": command,
            "value": value
        })
        
        topic = f"scada/commands/{device_id}"
        return await self.publish(topic, payload)


# Instancia global
mqtt_client = MQTTClient()
