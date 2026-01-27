"""
Driver de simulación para pruebas sin hardware físico.
Genera ondas senoidales, valores aleatorios y estáticos.
"""
import random
import math
import time
from typing import Any, Dict
from .base import IndustrialDriver

class SimulatorDriver(IndustrialDriver):
    async def connect(self) -> bool:
        # Siempre conectado
        self.connected = True
        return True

    async def disconnect(self):
        self.connected = False

    async def read_tag(self, tag_config: Dict[str, Any]) -> Any:
        # Simula una onda senoidal basada en el tiempo
        wave_type = tag_config.get("signal_type", "random")
        
        if wave_type == "sine":
            # 50 + 25 * sin(t) -> oscila entre 25 y 75
            return 50 + (25 * math.sin(time.time()))
        elif wave_type == "random":
            return random.uniform(0, 100)
        elif wave_type == "static":
            return 10
        elif wave_type == "ramp":
            # Rampa de 0 a 100
            return (time.time() * 10) % 100
        
        return 0
            
    async def write_tag(self, tag_config: Dict[str, Any], value: Any) -> bool:
        print(f"SIMULACIÓN: Escribiendo {value} en {tag_config}")
        return True
