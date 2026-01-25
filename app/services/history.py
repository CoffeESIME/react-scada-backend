"""
Servicio de Historial: Suscriptor MQTT -> TimescaleDB.
Persiste datos de tiempo real en la base de datos.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

import aiomqtt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_factory
from app.db.models import Metric, Tag

logger = logging.getLogger(__name__)


class HistoryService:
    """
    Servicio que suscribe a topics MQTT y persiste
    los valores en TimescaleDB como métricas históricas.
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._topics = ["scada/+/+"]  # scada/{device}/{tag}
    
    async def start(self) -> None:
        """Inicia el servicio de historial."""
        self._running = True
        self._task = asyncio.create_task(self._subscribe_loop())
        logger.info("History service started")
    
    async def stop(self) -> None:
        """Detiene el servicio."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("History service stopped")
    
    async def _subscribe_loop(self) -> None:
        """Loop principal de suscripción MQTT."""
        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=settings.mqtt_broker_host,
                    port=settings.mqtt_broker_port,
                    username=settings.mqtt_username,
                    password=settings.mqtt_password,
                    identifier=f"{settings.mqtt_client_id}-history"
                ) as client:
                    # Suscribirse a todos los topics de datos
                    for topic in self._topics:
                        await client.subscribe(topic)
                        logger.info(f"Subscribed to: {topic}")
                    
                    # Procesar mensajes
                    async for message in client.messages:
                        await self._process_message(message)
                        
            except aiomqtt.MqttError as e:
                logger.error(f"MQTT error: {e}. Reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                await asyncio.sleep(5)
    
    async def _process_message(self, message) -> None:
        """Procesa un mensaje MQTT y lo guarda en la DB."""
        try:
            topic = str(message.topic)
            payload = message.payload.decode()
            
            # Parsear topic: scada/{device}/{tag}
            parts = topic.split("/")
            if len(parts) < 3:
                return
            
            tag_name = f"{parts[1]}_{parts[2]}"
            
            # Parsear valor
            try:
                data = json.loads(payload)
                value = float(data.get("value", data))
                quality = int(data.get("quality", 192))
                timestamp = data.get("timestamp")
                if timestamp:
                    timestamp = datetime.fromisoformat(timestamp)
                else:
                    timestamp = datetime.utcnow()
            except (json.JSONDecodeError, ValueError):
                value = float(payload)
                quality = 192
                timestamp = datetime.utcnow()
            
            # Guardar en base de datos
            await self._save_metric(tag_name, value, quality, timestamp)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _save_metric(
        self, tag_name: str, value: float, 
        quality: int, timestamp: datetime
    ) -> None:
        """Guarda una métrica en TimescaleDB."""
        async with async_session_factory() as session:
            # Buscar tag por nombre (o crear si no existe)
            # Por ahora asumimos que el tag existe
            # TODO: Implementar cache de tags
            
            metric = Metric(
                tag_id=1,  # TODO: Resolver tag_id real
                value=value,
                quality=quality,
                timestamp=timestamp
            )
            
            session.add(metric)
            await session.commit()
            
            logger.debug(f"Saved metric: {tag_name}={value}")


# Instancia global
history_service = HistoryService()
