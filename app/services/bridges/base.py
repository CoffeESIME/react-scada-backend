"""
Clase base abstracta para drivers industriales.
Define la interfaz que todos los drivers deben implementar.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict

class IndustrialDriver(ABC):
    """
    Clase base abstracta. Todos los drivers (Modbus, OPCUA, etc.)
    DEBEN heredar de aquí e implementar estos métodos.
    """

    def __init__(self, connection_config: Dict[str, Any]):
        self.config = connection_config
        self.connected = False

    @abstractmethod
    async def connect(self) -> bool:
        """Establece conexión con el dispositivo físico."""
        pass

    @abstractmethod
    async def disconnect(self):
        """Cierra la conexión limpiamente."""
        pass

    @abstractmethod
    async def read_tag(self, tag_config: Dict[str, Any]) -> Any:
        """
        Lee un valor.
        tag_config: Parte JSON del tag (ej: registro 4001, nodeID).
        Retorna: El valor leído o None si falló.
        """
        pass
    
    @abstractmethod
    async def write_tag(self, tag_config: Dict[str, Any], value: Any) -> bool:
        """Escribe un valor al dispositivo."""
        pass
