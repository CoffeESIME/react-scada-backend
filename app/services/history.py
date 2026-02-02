"""
Servicio de Historial: Suscriptor MQTT -> TimescaleDB.
Persiste datos de tiempo real en la base de datos.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict

import aiomqtt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_factory
from app.db.models import Metric, Tag
from app.services.storage import save_metric

logger = logging.getLogger(__name__)


class HistoryService:
    """
    Servicio que suscribe a topics MQTT internos y persiste
    los valores en TimescaleDB como métricas históricas.
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # Topics internos donde engine.py y mqtt_listener.py publican datos normalizados
        self._topics = ["scada/tags/#"] 
        # Cache: MQTT Topic -> Tag ID
        self._topic_map: Dict[str, int] = {}
    
    async def start(self) -> None:
        """Inicia el servicio de historial."""
        self._running = True
        await self._load_topic_map()
        self._task = asyncio.create_task(self._subscribe_loop())
        logger.info("History service started")
    
    async def stop(self) -> None:
        """Detiene el servicio."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("History service stopped")
        
    async def _load_topic_map(self):
        """Carga el mapa de topics a IDs desde la BD."""
        try:
            async with async_session_factory() as session:
                query = select(Tag).where(Tag.is_enabled == True)
                result = await session.execute(query)
                tags = result.scalars().all()
                
                self._topic_map = {tag.mqtt_topic: tag.id for tag in tags}
                logger.info(f"History Service: Loaded {len(self._topic_map)} tags for persistence.")
        except Exception as e:
            logger.error(f"Error loading topic map in History Service: {e}")
    
    async def _subscribe_loop(self) -> None:
        """Loop principal de suscripción MQTT."""
        while self._running:
            try:
                # Si el mapa está vacío, intentamos recargar (ej: inicio rápido)
                if not self._topic_map:
                    await self._load_topic_map()
                
                async with aiomqtt.Client(
                    hostname=settings.mqtt_broker_host,
                    port=settings.mqtt_broker_port,
                    username=settings.mqtt_username,
                    password=settings.mqtt_password,
                    identifier=f"{settings.mqtt_client_id}-history"
                ) as client:
                    
                    # Suscribirse al wildcard de tags
                    for topic in self._topics:
                        await client.subscribe(topic)
                        logger.info(f"History subscribed to: {topic}")
                    
                    # Procesar mensajes
                    async for message in client.messages:
                        await self._process_message(message)
                        
            except aiomqtt.MqttError as e:
                logger.error(f"History MQTT error: {e}. Reconnecting...")
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in History loop: {e}")
                await asyncio.sleep(5)
    
    async def _process_message(self, message) -> None:
        """Procesa un mensaje MQTT y lo guarda en la DB."""
        try:
            topic = str(message.topic)
            
            # Buscar ID del tag
            # Si no está en el mapa, puede ser nuevo o no configurado
            tag_id = self._topic_map.get(topic)
            if not tag_id:
                # Opcional: Intentar recargar mapa si es desconocido? 
                # Por ahora ignoramos para rendimiento
                return # No gestionado
            
            payload = message.payload.decode()
            
            # Parsear valor JSON estandarizado
            try:
                data = json.loads(payload)
                # Formato esperado: {"value": 123, "quality": "GOOD", ...}
                value = float(data.get("value", 0.0))
                # quality puede venir como string "GOOD" o int. save_metric espera int normalmente,
                # pero app/services/storage.py define save_metric(tag_id, value, quality=192).
                # Revisemos si save_metric maneja timestamp.
                
                # Asumimos que viene el timestamp o usamos now.
                # Nota: save_metric generalmente usa datetime.utcnow() internamente si no se pasa.
                # Pero storage.py simple solo acepta (tag_id, value). Verifiquemos eso luego. 
                # Vamos a usar save_metric tal cual está en mqtt_listener.py
                
                await save_metric(tag_id=tag_id, value=value)
                
            except (json.JSONDecodeError, ValueError):
                logger.warning(f"Invalid payload for topic {topic}: {payload}")
            
        except Exception as e:
            logger.error(f"Error processing history message: {e}")


# Instancia global
history_service = HistoryService()
