"""
Driver Modbus TCP para comunicación con PLCs y dispositivos industriales.
Implementa polling periódico de registros Modbus.
"""
import asyncio
import logging
from typing import Dict, Optional, List, Callable
from dataclasses import dataclass

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

logger = logging.getLogger(__name__)


@dataclass
class ModbusRegister:
    """Configuración de un registro Modbus a leer."""
    address: int
    count: int = 1
    function_code: int = 3  # 3=Holding, 4=Input
    tag_name: str = ""
    unit_id: int = 1
    scale: float = 1.0
    offset: float = 0.0


class ModbusBridge:
    """
    Bridge para comunicación Modbus TCP.
    Soporta polling periódico y lectura bajo demanda.
    """
    
    def __init__(
        self,
        host: str,
        port: int = 502,
        poll_interval: float = 1.0,
        on_data_callback: Optional[Callable] = None
    ):
        self.host = host
        self.port = port
        self.poll_interval = poll_interval
        self.on_data_callback = on_data_callback
        
        self._client: Optional[AsyncModbusTcpClient] = None
        self._registers: Dict[str, ModbusRegister] = {}
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
    
    async def connect(self) -> bool:
        """Establece conexión con el dispositivo Modbus."""
        try:
            self._client = AsyncModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=5
            )
            connected = await self._client.connect()
            if connected:
                logger.info(f"Connected to Modbus device at {self.host}:{self.port}")
            return connected
        except Exception as e:
            logger.error(f"Failed to connect to Modbus: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Cierra la conexión Modbus."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
        if self._client:
            self._client.close()
            logger.info(f"Disconnected from Modbus device at {self.host}")
    
    def add_register(self, tag_name: str, register: ModbusRegister) -> None:
        """Agrega un registro al pool de polling."""
        register.tag_name = tag_name
        self._registers[tag_name] = register
    
    async def read_register(self, register: ModbusRegister) -> Optional[float]:
        """
        Lee un registro Modbus individual.
        
        Returns:
            Valor escalado o None si hay error.
        """
        if not self._client or not self._client.connected:
            logger.warning("Modbus client not connected")
            return None
        
        try:
            if register.function_code == 3:
                result = await self._client.read_holding_registers(
                    address=register.address,
                    count=register.count,
                    slave=register.unit_id
                )
            elif register.function_code == 4:
                result = await self._client.read_input_registers(
                    address=register.address,
                    count=register.count,
                    slave=register.unit_id
                )
            else:
                logger.error(f"Unsupported function code: {register.function_code}")
                return None
            
            if result.isError():
                logger.error(f"Modbus read error: {result}")
                return None
            
            # Aplicar escala y offset
            raw_value = result.registers[0]
            scaled_value = (raw_value * register.scale) + register.offset
            return scaled_value
            
        except ModbusException as e:
            logger.error(f"Modbus exception: {e}")
            return None
    
    async def write_register(
        self,
        address: int,
        value: int,
        unit_id: int = 1
    ) -> bool:
        """
        Escribe un valor en un registro Modbus.
        
        Returns:
            True si la escritura fue exitosa.
        """
        if not self._client or not self._client.connected:
            return False
        
        try:
            result = await self._client.write_register(
                address=address,
                value=value,
                slave=unit_id
            )
            return not result.isError()
        except ModbusException as e:
            logger.error(f"Modbus write error: {e}")
            return False
    
    async def start_polling(self) -> None:
        """Inicia el polling periódico de registros."""
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(f"Started Modbus polling with interval {self.poll_interval}s")
    
    async def _poll_loop(self) -> None:
        """Loop principal de polling."""
        while self._running:
            readings: Dict[str, float] = {}
            
            for tag_name, register in self._registers.items():
                value = await self.read_register(register)
                if value is not None:
                    readings[tag_name] = value
            
            # Notificar lecturas
            if self.on_data_callback and readings:
                await self.on_data_callback(readings)
            
            await asyncio.sleep(self.poll_interval)


# Ejemplo de uso
async def example_usage():
    """Ejemplo de cómo usar el ModbusBridge."""
    
    async def on_data(readings: Dict[str, float]):
        for tag, value in readings.items():
            print(f"{tag}: {value}")
    
    bridge = ModbusBridge(
        host="192.168.1.100",
        port=502,
        poll_interval=1.0,
        on_data_callback=on_data
    )
    
    # Agregar registros a monitorear
    bridge.add_register("motor_speed", ModbusRegister(
        address=0,
        count=1,
        function_code=3,
        scale=0.1,
        offset=0
    ))
    
    bridge.add_register("temperature", ModbusRegister(
        address=10,
        count=1,
        function_code=4,
        scale=0.01,
        offset=-50
    ))
    
    if await bridge.connect():
        await bridge.start_polling()
        await asyncio.sleep(10)  # Monitorear por 10 segundos
        await bridge.disconnect()
