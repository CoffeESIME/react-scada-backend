"""
Factory Method para instanciar el driver correcto según el protocolo.
"""
from typing import Dict, Any
from .modbus import ModbusDriver
from .opcua import OpcUaDriver
from .simulator import SimulatorDriver
from .mqtt_bridge import MqttBridge
from .base import IndustrialDriver

class ProtocolFactory:
    """Fabrica de drivers industriales."""
    
    @staticmethod
    def get_driver(protocol_type: str, connection_config: Dict[str, Any]) -> IndustrialDriver:
        """
        Retorna una instancia del driver correspondiente al protocolo.
        
        Args:
            protocol_type: "modbus", "opcua", "simulated", "mqtt", etc.
            connection_config: Diccionario con la configuración de conexión del tag.
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
        elif p_type in ("simulated", "simulator"):
            return SimulatorDriver(connection_config)
        elif p_type == "mqtt":
            return MqttBridge(connection_config)
        else:
            raise ValueError(f"Protocolo '{protocol_type}' no soportado por ProtocolFactory")
