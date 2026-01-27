"""
Implementación del driver Modbus TCP usando pymodbus.
"""
import asyncio
from typing import Any, Dict
from pymodbus.client import AsyncModbusTcpClient
from .base import IndustrialDriver

class ModbusDriver(IndustrialDriver):
    def __init__(self, connection_config: Dict[str, Any]):
        super().__init__(connection_config)
        self.ip = connection_config.get("ip")
        self.port = connection_config.get("port", 502)
        # pymodbus client
        self.client = AsyncModbusTcpClient(self.ip, port=self.port)

    async def connect(self) -> bool:
        if not self.client.connected:
            self.connected = await self.client.connect()
        return self.connected

    async def disconnect(self):
        if self.client.connected:
            self.client.close()
            self.connected = False

    async def read_tag(self, tag_config: Dict[str, Any]) -> Any:
        if not self.connected:
            await self.connect()
            
        register = tag_config.get("register")
        count = tag_config.get("count", 1)
        slave = tag_config.get("slave_id", 1)
        # 1=Holding, 2=Input, 3=Coil, 4=Discrete Input (esto varía según el driver, simplificamos)
        # Asumiremos Holding Registers (FC03) por defecto para el ejemplo
        
        try:
            # pymodbus devuelve un ModbusResponse o Exception
            result = await self.client.read_holding_registers(
                address=register, 
                count=count, 
                slave=slave
            )
            if not result.isError():
                # Retorna el primer registro (o la lista completa si count > 1)
                # Aquí se podría mejorar la decodificación de tipos (float, int32, etc.)
                if count == 1:
                    return result.registers[0]
                return result.registers
            else:
                return None
        except Exception as e:
            print(f"Error Modbus: {e}")
            return None

    async def write_tag(self, tag_config: Dict[str, Any], value: Any) -> bool:
        if not self.connected:
            await self.connect()

        register = tag_config.get("register")
        slave = tag_config.get("slave_id", 1)
        
        try:
            # Asumimos escritura de un solo registro (FC06)
            # Para múltiples, write_registers (FC16)
            result = await self.client.write_register(
                address=register,
                value=int(value),
                slave=slave
            )
            return not result.isError()
        except Exception as e:
            print(f"Error Modbus Write: {e}")
            return False
