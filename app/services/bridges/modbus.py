"""
Implementación del driver Modbus TCP usando pyModbusTCP.
Más simple y ligero que pymodbus para comunicación básica.
"""
import asyncio
import logging
from typing import Any, Dict, Optional, List
from pyModbusTCP.client import ModbusClient
from .base import IndustrialDriver

logger = logging.getLogger(__name__)


class ModbusDriver(IndustrialDriver):
    """
    Driver Modbus TCP usando pyModbusTCP.
    
    connection_config esperado:
    {
        "ip": "192.168.0.155",
        "port": 502,           # Opcional, default 502
        "unit_id": 1,          # Opcional, default 1
        "register": 0,         # Dirección del registro
        "count": 1,            # Cantidad de registros a leer
        "register_type": "holding"  # holding, input, coil, discrete
    }
    """
    
    # Cache de conexiones para reutilizar
    _connections: Dict[str, ModbusClient] = {}
    
    def __init__(self, connection_config: Dict[str, Any]):
        super().__init__(connection_config)
        # Soportar ambas claves: "ip" o "host"
        self.ip = connection_config.get("ip") or connection_config.get("host")
        self.port = connection_config.get("port", 502)
        self.unit_id = connection_config.get("unit_id", 1)
        self.client: Optional[ModbusClient] = None
        
        # Debug: mostrar configuración recibida
        logger.info(f"[MODBUS] Config recibida: {connection_config}")
        logger.info(f"[MODBUS] IP: {self.ip}, Port: {self.port}, Unit: {self.unit_id}")
        
        if self.ip:
            self._connection_key = f"{self.ip}:{self.port}:{self.unit_id}"
        else:
            self._connection_key = ""
            logger.error(f"[MODBUS] IP no configurada! Config: {connection_config}")

    async def connect(self) -> bool:
        """Conecta al dispositivo Modbus TCP."""
        # Validar que tenemos IP
        if not self.ip or not isinstance(self.ip, str):
            logger.error(f"[MODBUS] IP inválida: {self.ip} (tipo: {type(self.ip)})")
            return False
        
        try:
            # Reutilizar conexión existente si está abierta
            if self._connection_key in ModbusDriver._connections:
                self.client = ModbusDriver._connections[self._connection_key]
                if self.client.is_open:
                    self.connected = True
                    return True
            
            # Crear nueva conexión
            self.client = ModbusClient(
                host=self.ip,
                port=self.port,
                unit_id=self.unit_id,
                auto_open=True,
                timeout=3.0
            )
            
            # Intentar abrir (pyModbusTCP es síncrono)
            connected = await asyncio.to_thread(self.client.open)
            
            if connected:
                ModbusDriver._connections[self._connection_key] = self.client
                self.connected = True
                logger.info(f"[MODBUS] Conectado a {self.ip}:{self.port}")
            else:
                logger.warning(f"[MODBUS] No se pudo conectar a {self.ip}:{self.port}")
                self.connected = False
                
            return self.connected
            
        except Exception as e:
            logger.error(f"[MODBUS] Error de conexión: {e}")
            self.connected = False
            return False

    async def disconnect(self):
        """Cierra la conexión Modbus."""
        # No cerramos realmente para reutilizar, pero marcamos como desconectado
        self.connected = False
        # Si quisieras cerrar de verdad:
        # if self.client and self.client.is_open:
        #     self.client.close()

    async def read_tag(self, tag_config: Dict[str, Any]) -> Any:
        """
        Lee un registro Modbus.
        
        tag_config:
        {
            "register": 0,           # Dirección del registro
            "count": 1,              # Cantidad de registros (default 1)
            "register_type": "holding",  # holding, input, coil, discrete
            "data_type": "uint16"    # uint16, int16, float32, etc. (futuro)
        }
        """
        if not self.connected:
            await self.connect()
            
        if not self.client or not self.client.is_open:
            logger.warning("[MODBUS] Cliente no conectado para lectura")
            return None
            
        register = tag_config.get("register", 0)
        count = tag_config.get("count", 1)
        reg_type = tag_config.get("register_type", "holding")
        
        try:
            result: Optional[List[int]] = None
            
            if reg_type == "holding":
                result = await asyncio.to_thread(
                    self.client.read_holding_registers, register, count
                )
            elif reg_type == "input":
                result = await asyncio.to_thread(
                    self.client.read_input_registers, register, count
                )
            elif reg_type == "coil":
                result = await asyncio.to_thread(
                    self.client.read_coils, register, count
                )
            elif reg_type == "discrete":
                result = await asyncio.to_thread(
                    self.client.read_discrete_inputs, register, count
                )
            else:
                logger.warning(f"[MODBUS] Tipo de registro desconocido: {reg_type}")
                return None
            
            if result is not None:
                # Retorna un solo valor si count=1, lista si count > 1
                if count == 1:
                    return result[0]
                return result
            else:
                logger.warning(f"[MODBUS] Lectura fallida en registro {register}")
                return None
                
        except Exception as e:
            logger.error(f"[MODBUS] Error de lectura: {e}")
            return None

    async def write_tag(self, tag_config: Dict[str, Any], value: Any) -> bool:
        """
        Escribe un valor en un registro Modbus.
        
        tag_config:
        {
            "register": 0,
            "register_type": "holding"  # holding o coil
        }
        """
        if not self.connected:
            await self.connect()
            
        if not self.client or not self.client.is_open:
            logger.warning("[MODBUS] Cliente no conectado para escritura")
            return False
            
        register = tag_config.get("register", 0)
        reg_type = tag_config.get("register_type", "holding")
        
        try:
            success = False
            
            if reg_type == "holding":
                # Escribir un solo registro (FC06)
                success = await asyncio.to_thread(
                    self.client.write_single_register, register, int(value)
                )
            elif reg_type == "coil":
                # Escribir un solo coil (FC05)
                success = await asyncio.to_thread(
                    self.client.write_single_coil, register, bool(value)
                )
            else:
                logger.warning(f"[MODBUS] Escritura no soportada para tipo: {reg_type}")
                return False
            
            if success:
                logger.debug(f"[MODBUS] Escrito {value} en registro {register}")
            else:
                logger.warning(f"[MODBUS] Escritura fallida en registro {register}")
                
            return success
            
        except Exception as e:
            logger.error(f"[MODBUS] Error de escritura: {e}")
            return False

