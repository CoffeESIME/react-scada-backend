"""
Schemas avanzados para Tags con validación polimórfica.
Valida connection_config dinámicamente según source_protocol.
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, model_validator, ConfigDict
import re

from app.db.models import ProtocolType, AlarmSeverity


# ============ Connection Config Schemas (Submodelos) ============

class ModbusConfig(BaseModel):
    """Config requerida para protocolo Modbus."""
    host: str = Field(..., description="IP del dispositivo Modbus")
    port: int = Field(default=502, ge=1, le=65535)
    register: int = Field(..., ge=0, description="Dirección del registro")
    slave_id: int = Field(default=1, ge=0, le=255)
    register_type: str = Field(default="holding", pattern="^(holding|input|coil|discrete)$")


class OpcuaConfig(BaseModel):
    """Config requerida para protocolo OPC UA."""
    url: str = Field(..., description="URL del servidor OPC UA")
    node_id: str = Field(..., description="NodeID del nodo a leer")


class MqttExternalConfig(BaseModel):
    """Config requerida para protocolo MQTT externo."""
    topic: str = Field(..., description="Topic MQTT a suscribir")
    json_key: Optional[str] = Field(None, description="Clave JSON para extraer el valor")


class SimulatedConfig(BaseModel):
    """Config requerida para protocolo simulado."""
    signal_type: str = Field(
        default="sine", 
        pattern="^(sine|random|static|ramp)$",
        description="Tipo de señal: sine, random, static, ramp"
    )
    min: float = Field(default=0.0)
    max: float = Field(default=100.0)


# ============ Alarm Embedded Schema ============

class AlarmDefinitionEmbedded(BaseModel):
    """Alarma embebida para crear junto con el Tag."""
    severity: AlarmSeverity = AlarmSeverity.WARNING
    message: str = Field(..., min_length=1, max_length=500)
    limits: Dict[str, float] = Field(
        default={},
        description="Umbrales: HH, H, L, LL"
    )
    deadband: float = Field(default=0.0, ge=0.0)
    is_active: bool = True


# ============ Tag Create/Update Schemas ============

class TagCreate(BaseModel):
    """Schema para crear un Tag con validación polimórfica."""
    model_config = ConfigDict(from_attributes=True)
    
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    unit: Optional[str] = Field(None, max_length=50)
    
    source_protocol: ProtocolType = ProtocolType.SIMULATED
    connection_config: Dict[str, Any] = Field(default_factory=dict)
    
    scan_rate_ms: int = Field(default=1000, ge=100, le=3600000)
    mqtt_topic: Optional[str] = Field(None, max_length=200)
    is_enabled: bool = True
    
    # Alarma opcional embebida
    alarm: Optional[AlarmDefinitionEmbedded] = None
    
    @model_validator(mode="after")
    def validate_connection_config(self):
        """Valida connection_config según el protocolo seleccionado."""
        protocol = self.source_protocol
        config = self.connection_config
        
        try:
            if protocol == ProtocolType.MODBUS:
                ModbusConfig(**config)
            elif protocol == ProtocolType.OPCUA:
                OpcuaConfig(**config)
            elif protocol == ProtocolType.MQTT:
                MqttExternalConfig(**config)
            elif protocol == ProtocolType.SIMULATED:
                SimulatedConfig(**config)
        except Exception as e:
            raise ValueError(f"connection_config inválido para {protocol.value}: {e}")
        
        return self
    
    @model_validator(mode="after")
    def generate_mqtt_topic(self):
        """Genera mqtt_topic automáticamente si no se proporciona."""
        if not self.mqtt_topic:
            # Normalizar nombre: lowercase, reemplazar espacios con _
            normalized = re.sub(r'[^a-zA-Z0-9_]', '_', self.name.lower())
            self.mqtt_topic = f"scada/tags/{normalized}"
        return self


class TagUpdate(BaseModel):
    """Schema para actualizar un Tag (todos los campos opcionales)."""
    model_config = ConfigDict(from_attributes=True)
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    unit: Optional[str] = Field(None, max_length=50)
    
    source_protocol: Optional[ProtocolType] = None
    connection_config: Optional[Dict[str, Any]] = None
    
    scan_rate_ms: Optional[int] = Field(None, ge=100, le=3600000)
    mqtt_topic: Optional[str] = Field(None, max_length=200)
    is_enabled: Optional[bool] = None
    
    # Alarma opcional para actualizar/crear
    alarm: Optional[AlarmDefinitionEmbedded] = None
    
    @model_validator(mode="after")
    def validate_connection_config_if_present(self):
        """Valida connection_config solo si ambos campos están presentes."""
        if self.source_protocol and self.connection_config:
            try:
                if self.source_protocol == ProtocolType.MODBUS:
                    ModbusConfig(**self.connection_config)
                elif self.source_protocol == ProtocolType.OPCUA:
                    OpcuaConfig(**self.connection_config)
                elif self.source_protocol == ProtocolType.MQTT:
                    MqttExternalConfig(**self.connection_config)
                elif self.source_protocol == ProtocolType.SIMULATED:
                    SimulatedConfig(**self.connection_config)
            except Exception as e:
                raise ValueError(f"connection_config inválido: {e}")
        return self



# ============ Tag Write Schema ============

class TagWrite(BaseModel):
    """Schema para escribir un valor en un Tag."""
    value: Any = Field(..., description="Valor a escribir en el tag")


# ============ Tag Read Schemas ============

class AlarmDefinitionRead(BaseModel):
    """Schema de respuesta para AlarmDefinition."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    tag_id: int
    severity: AlarmSeverity
    message: str
    limits: Dict[str, float]
    deadband: float
    is_active: bool


class TagRead(BaseModel):
    """Schema de respuesta para Tag con alarma incluida."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    description: Optional[str]
    unit: Optional[str]
    
    source_protocol: ProtocolType
    connection_config: Dict[str, Any]
    
    scan_rate_ms: int
    mqtt_topic: str
    is_enabled: bool
    
    # Alarma relacionada (puede ser None)
    alarm_definition: Optional[AlarmDefinitionRead] = None


class TagList(BaseModel):
    """Schema para listado paginado de tags."""
    items: List[TagRead]
    total: int
    page: int
    page_size: int
    pages: int
