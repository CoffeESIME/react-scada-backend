"""
Pydantic Schemas para validación de datos SCADA.
Actualizado para coincidir con los nuevos modelos SQLAlchemy.
"""
from datetime import datetime
from typing import Optional, List, Any, Dict

from pydantic import BaseModel, Field

from app.db.models import AlarmSeverity, ProtocolType

# ============ Tag Schemas ============

class TagBase(BaseModel):
    """Campos base de un Tag."""
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    unit: Optional[str] = Field(None, max_length=50)
    
    source_protocol: ProtocolType = ProtocolType.SIMULATED
    connection_config: Dict[str, Any] = {}
    scan_rate_ms: int = 1000
    mqtt_topic: str
    is_enabled: bool = True

class TagCreate(TagBase):
    """Schema para crear un Tag."""
    pass

class TagRead(TagBase):
    """Schema de respuesta para Tag."""
    id: int
    
    class Config:
        from_attributes = True

# ============ Metric Schemas ============

class MetricBase(BaseModel):
    tag_id: int
    value: float
    quality: int = 192

class MetricCreate(MetricBase):
    """Métrica entrante (puede no traer timestamp si es current)."""
    time: Optional[datetime] = None

class MetricRead(MetricBase):
    """Métrica histórica con timestamp."""
    time: datetime

    class Config:
        from_attributes = True

# ============ Screen Schemas ============
# Reemplaza la antigua lógica de Nodes/Edges individuales

class ScreenBase(BaseModel):
    name: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_home: bool = False
    layout_data: Dict[str, Any] = {} # Contiene {nodes: [], edges: []} de React Flow

class ScreenCreate(ScreenBase):
    pass

class ScreenUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    is_home: Optional[bool] = None
    layout_data: Optional[Dict[str, Any]] = None

class ScreenRead(ScreenBase):
    id: int

    class Config:
        from_attributes = True

# ============ Alarm Schemas ============

class AlarmDefinitionBase(BaseModel):
    severity: AlarmSeverity = AlarmSeverity.WARNING
    message: str
    limits: Dict[str, float] = {} # Ej: {"HH": 90.0, "L": 10.0}
    deadband: float = 0.0
    is_active: bool = True

class AlarmDefinitionCreate(AlarmDefinitionBase):
    tag_id: int

class AlarmDefinitionRead(AlarmDefinitionBase):
    id: int
    tag_id: int

    class Config:
        from_attributes = True

class AlarmEventRead(BaseModel):
    id: int
    definition_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    ack_time: Optional[datetime] = None
    ack_user_id: Optional[int] = None
    trigger_value: float
    status: str

    class Config:
        from_attributes = True
