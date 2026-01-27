"""
Factory Method para instanciar el driver correcto según el protocolo.
"""
from typing import Dict, Any
from .modbus import ModbusDriver
from .opcua import OpcUaDriver
from .simulator import SimulatorDriver
from .base import IndustrialDriver

class ProtocolFactory:
    """Fabrica de drivers industriales."""
    
    @staticmethod
    def get_driver(protocol_type: str, connection_config: Dict[str, Any]) -> IndustrialDriver:
        """
        Retorna una instancia del driver correspondiente.
        
        Args:
            protocol_type: "modbus", "opcua", "simulated", etc.
            connection_config: Diccionario con IP, Puerto, etc.
        """
        # Si es un Enum, obtenemos su valor ("modbus", "opcua", etc.)
        if hasattr(protocol_type, "value"):
            p_type = str(protocol_type.value).lower()
        else:
            p_type = str(protocol_type).lower()
            
        # Limpieza extra en caso de que venga como "ProtocolType.MODBUS"
        if "protocoltype." in p_type:
            p_type = p_type.split(".")[-1]
        
        if p_type == "modbus":
            return ModbusDriver(connection_config)
        elif p_type == "opcua":
            return OpcUaDriver(connection_config)
        elif p_type == "simulated" or p_type == "simulator":
            return SimulatorDriver(connection_config)
        else:
            # Fallback seguro: Simulator o Error
            # Por ahora lanzamos error para detectar configs malas
            raise ValueError(f"Protocolo {protocol_type} no soportado")
