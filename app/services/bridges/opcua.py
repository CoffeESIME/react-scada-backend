"""
Cliente OPC UA para comunicación con PLCs y sistemas SCADA.
Implementa suscripciones a nodos OPC UA.
"""
import asyncio
import logging
from typing import Dict, Optional, List, Callable, Any
from dataclasses import dataclass
from datetime import datetime

from asyncua import Client, ua
from asyncua.common.subscription import DataChangeNotif

logger = logging.getLogger(__name__)


@dataclass
class OPCUANode:
    """Configuración de un nodo OPC UA a suscribir."""
    node_id: str  # Ej: "ns=2;s=Channel1.Device1.Tag1"
    tag_name: str = ""
    scale: float = 1.0
    offset: float = 0.0


class SubscriptionHandler:
    """
    Handler para notificaciones de cambio de datos OPC UA.
    """
    
    def __init__(self, callback: Callable[[str, Any, datetime], None]):
        self.callback = callback
    
    def datachange_notification(self, node, val, data):
        """Llamado cuando un valor suscrito cambia."""
        try:
            timestamp = data.monitored_item.Value.SourceTimestamp or datetime.utcnow()
            node_id = node.nodeid.to_string()
            self.callback(node_id, val, timestamp)
        except Exception as e:
            logger.error(f"Error in datachange callback: {e}")


class OPCUABridge:
    """
    Bridge para comunicación OPC UA.
    Soporta suscripciones y lectura/escritura bajo demanda.
    """
    
    def __init__(
        self,
        endpoint: str,
        on_data_callback: Optional[Callable] = None,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Args:
            endpoint: URL del servidor OPC UA (ej: "opc.tcp://localhost:4840")
            on_data_callback: Función a llamar cuando hay nuevos datos
            username: Usuario para autenticación (opcional)
            password: Contraseña para autenticación (opcional)
        """
        self.endpoint = endpoint
        self.on_data_callback = on_data_callback
        self.username = username
        self.password = password
        
        self._client: Optional[Client] = None
        self._subscription = None
        self._nodes: Dict[str, OPCUANode] = {}
        self._node_id_to_tag: Dict[str, str] = {}
        self._running = False
    
    async def connect(self) -> bool:
        """Establece conexión con el servidor OPC UA."""
        try:
            self._client = Client(url=self.endpoint)
            
            # Configurar autenticación si se proporcionó
            if self.username and self.password:
                self._client.set_user(self.username)
                self._client.set_password(self.password)
            
            await self._client.connect()
            logger.info(f"Connected to OPC UA server at {self.endpoint}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to OPC UA server: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Cierra la conexión OPC UA."""
        self._running = False
        
        if self._subscription:
            await self._subscription.delete()
            self._subscription = None
        
        if self._client:
            await self._client.disconnect()
            logger.info(f"Disconnected from OPC UA server")
    
    def add_node(self, tag_name: str, node: OPCUANode) -> None:
        """Agrega un nodo al pool de suscripción."""
        node.tag_name = tag_name
        self._nodes[tag_name] = node
        self._node_id_to_tag[node.node_id] = tag_name
    
    async def read_node(self, node_id: str) -> Optional[Any]:
        """
        Lee el valor actual de un nodo OPC UA.
        
        Args:
            node_id: ID del nodo (ej: "ns=2;s=Tag1")
            
        Returns:
            Valor del nodo o None si hay error.
        """
        if not self._client:
            logger.warning("OPC UA client not connected")
            return None
        
        try:
            node = self._client.get_node(node_id)
            value = await node.read_value()
            return value
        except Exception as e:
            logger.error(f"Failed to read OPC UA node {node_id}: {e}")
            return None
    
    async def write_node(self, node_id: str, value: Any) -> bool:
        """
        Escribe un valor en un nodo OPC UA.
        
        Args:
            node_id: ID del nodo destino
            value: Valor a escribir
            
        Returns:
            True si la escritura fue exitosa.
        """
        if not self._client:
            return False
        
        try:
            node = self._client.get_node(node_id)
            await node.write_value(value)
            logger.debug(f"Wrote value {value} to node {node_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to write to OPC UA node {node_id}: {e}")
            return False
    
    async def subscribe_all(self, publish_interval: int = 500) -> bool:
        """
        Crea suscripciones para todos los nodos agregados.
        
        Args:
            publish_interval: Intervalo de publicación en milisegundos.
            
        Returns:
            True si las suscripciones fueron exitosas.
        """
        if not self._client or not self._nodes:
            return False
        
        try:
            # Crear manejador de datos
            handler = SubscriptionHandler(self._on_data_change)
            
            # Crear suscripción
            self._subscription = await self._client.create_subscription(
                period=publish_interval,
                handler=handler
            )
            
            # Suscribirse a cada nodo
            for node_config in self._nodes.values():
                node = self._client.get_node(node_config.node_id)
                await self._subscription.subscribe_data_change(node)
                logger.debug(f"Subscribed to node: {node_config.node_id}")
            
            self._running = True
            logger.info(f"Created OPC UA subscriptions for {len(self._nodes)} nodes")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create OPC UA subscriptions: {e}")
            return False
    
    def _on_data_change(self, node_id: str, value: Any, timestamp: datetime) -> None:
        """Callback interno para procesar cambios de datos."""
        tag_name = self._node_id_to_tag.get(node_id)
        if not tag_name:
            return
        
        node_config = self._nodes.get(tag_name)
        if node_config:
            # Aplicar escala y offset
            try:
                scaled_value = (float(value) * node_config.scale) + node_config.offset
            except (TypeError, ValueError):
                scaled_value = value
            
            # Notificar callback externo
            if self.on_data_callback:
                asyncio.create_task(
                    self.on_data_callback(tag_name, scaled_value, timestamp)
                )
    
    async def browse_nodes(self, start_node_id: str = "i=85") -> List[Dict]:
        """
        Navega el árbol de nodos OPC UA.
        
        Args:
            start_node_id: ID del nodo raíz (default: Objects folder)
            
        Returns:
            Lista de nodos encontrados.
        """
        if not self._client:
            return []
        
        nodes = []
        try:
            root = self._client.get_node(start_node_id)
            children = await root.get_children()
            
            for child in children:
                node_info = {
                    "node_id": child.nodeid.to_string(),
                    "browse_name": (await child.read_browse_name()).Name,
                    "node_class": (await child.read_node_class()).name
                }
                nodes.append(node_info)
                
        except Exception as e:
            logger.error(f"Failed to browse OPC UA nodes: {e}")
        
        return nodes


# Ejemplo de uso
async def example_usage():
    """Ejemplo de cómo usar el OPCUABridge."""
    
    async def on_data(tag: str, value: Any, timestamp: datetime):
        print(f"{timestamp} - {tag}: {value}")
    
    bridge = OPCUABridge(
        endpoint="opc.tcp://localhost:4840",
        on_data_callback=on_data
    )
    
    # Agregar nodos a monitorear
    bridge.add_node("motor_speed", OPCUANode(
        node_id="ns=2;s=Channel1.Device1.MotorSpeed",
        scale=1.0,
        offset=0
    ))
    
    bridge.add_node("temperature", OPCUANode(
        node_id="ns=2;s=Channel1.Device1.Temperature",
        scale=0.01,
        offset=-273.15  # Kelvin a Celsius
    ))
    
    if await bridge.connect():
        await bridge.subscribe_all()
        await asyncio.sleep(60)  # Monitorear por 60 segundos
        await bridge.disconnect()
