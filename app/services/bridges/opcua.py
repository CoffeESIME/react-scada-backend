"""
Implementación del driver OPC UA usando asyncua.
"""
import asyncio
from typing import Any, Dict
from asyncua import Client
from .base import IndustrialDriver

class OpcUaDriver(IndustrialDriver):
    def __init__(self, connection_config: Dict[str, Any]):
        super().__init__(connection_config)
        self.url = connection_config.get("url", "opc.tcp://localhost:4840")
        self.client = Client(url=self.url)
        

    async def connect(self) -> bool:
        try:
            await self.client.connect()
            self.connected = True
            return True
        except Exception as e:
            print(f"Error OPC UA Connect: {e}")
            self.connected = False
            return False

    async def disconnect(self):
        if self.connected:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.connected = False

    async def read_tag(self, tag_config: Dict[str, Any]) -> Any:
        
        if not self.connected:
            await self.connect()
            
        node_id = tag_config.get("node_id")
        if not node_id:
            return None

        try:
            node = self.client.get_node(node_id)
            value = await node.read_value()
            return value
        except Exception as e:
            print(f"Error OPC UA Read: {e}")
            
            await self.disconnect()
            return None

    async def write_tag(self, tag_config: Dict[str, Any], value: Any) -> bool:
        if not self.connected:
            await self.connect()

        node_id = tag_config.get("node_id")
        if not node_id:
            return False
            
        try:
            node = self.client.get_node(node_id)
            
            
            
            await node.write_value(value)
            return True
        except Exception as e:
            print(f"Error OPC UA Write: {e}")
            return False
