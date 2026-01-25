"""
Pydantic Schemas para validación de datos SCADA.
Nodos, Edges, Tags y Pantallas.
"""
from datetime import datetime
from typing import Optional, List, Any, Dict

from pydantic import BaseModel, Field

from app.db.models import TagDataType, NodeType, AlarmSeverity, AlarmStatus


# ============ Tag Schemas ============

class TagBase(BaseModel):
    """Campos base de un Tag."""
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    data_type: TagDataType = TagDataType.FLOAT
    unit: Optional[str] = Field(None, max_length=50)
    source_type: str = Field("mqtt", max_length=50)
    source_address: Optional[str] = Field(None, max_length=255)


class TagCreate(TagBase):
    """Schema para crear un Tag."""
    low_limit: Optional[float] = None
    high_limit: Optional[float] = None
    low_low_limit: Optional[float] = None
    high_high_limit: Optional[float] = None


class TagRead(TagBase):
    """Schema de respuesta para Tag."""
    id: int
    current_value: Optional[str] = None
    last_updated: Optional[datetime] = None
    low_limit: Optional[float] = None
    high_limit: Optional[float] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class TagWithMetrics(TagRead):
    """Tag con sus métricas históricas."""
    metrics: List["MetricRead"] = []


# ============ Metric Schemas ============

class MetricRead(BaseModel):
    """Schema de respuesta para Métrica."""
    id: int
    tag_id: int
    value: float
    timestamp: datetime
    quality: int = 192
    
    class Config:
        from_attributes = True


class MetricCreate(BaseModel):
    """Schema para crear una Métrica."""
    tag_id: int
    value: float
    timestamp: Optional[datetime] = None
    quality: int = 192


# ============ Alarm Schemas ============

class AlarmRead(BaseModel):
    """Schema de respuesta para Alarma."""
    id: int
    tag_id: Optional[int]
    severity: AlarmSeverity
    status: AlarmStatus
    message: str
    triggered_value: Optional[float]
    triggered_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class AlarmAcknowledge(BaseModel):
    """Schema para reconocer una alarma."""
    alarm_id: int
    user_id: int


# ============ Node Schemas ============

class NodeBase(BaseModel):
    """Campos base de un Nodo."""
    node_id: str = Field(..., max_length=100)
    node_type: NodeType = NodeType.GAUGE
    label: Optional[str] = Field(None, max_length=100)
    position_x: float = 0
    position_y: float = 0
    width: Optional[float] = None
    height: Optional[float] = None
    tag_id: Optional[int] = None
    config: Optional[Dict[str, Any]] = None


class NodeCreate(NodeBase):
    """Schema para crear un Nodo."""
    screen_id: int


class NodeRead(NodeBase):
    """Schema de respuesta para Nodo."""
    id: int
    screen_id: int
    
    class Config:
        from_attributes = True


class NodeUpdate(BaseModel):
    """Schema para actualizar un Nodo."""
    label: Optional[str] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    tag_id: Optional[int] = None
    config: Optional[Dict[str, Any]] = None


# ============ Edge Schemas ============

class EdgeBase(BaseModel):
    """Campos base de un Edge."""
    edge_id: str = Field(..., max_length=100)
    source_node_id: str = Field(..., max_length=100)
    target_node_id: str = Field(..., max_length=100)
    source_handle: Optional[str] = Field(None, max_length=50)
    target_handle: Optional[str] = Field(None, max_length=50)
    edge_type: str = Field("default", max_length=50)
    animated: bool = False
    style: Optional[Dict[str, Any]] = None


class EdgeCreate(EdgeBase):
    """Schema para crear un Edge."""
    screen_id: int


class EdgeRead(EdgeBase):
    """Schema de respuesta para Edge."""
    id: int
    screen_id: int
    
    class Config:
        from_attributes = True


# ============ Screen Schemas ============

class ScreenBase(BaseModel):
    """Campos base de una Pantalla."""
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class ScreenCreate(ScreenBase):
    """Schema para crear una Pantalla."""
    viewport_x: float = 0
    viewport_y: float = 0
    viewport_zoom: float = 1
    nodes: List[NodeBase] = []
    edges: List[EdgeBase] = []


class ScreenRead(ScreenBase):
    """Schema de respuesta para Pantalla."""
    id: int
    thumbnail_url: Optional[str] = None
    viewport_x: float
    viewport_y: float
    viewport_zoom: float
    is_default: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ScreenWithElements(ScreenRead):
    """Pantalla con todos sus nodos y edges."""
    nodes: List[NodeRead] = []
    edges: List[EdgeRead] = []


class ScreenUpdate(BaseModel):
    """Schema para actualizar una Pantalla."""
    name: Optional[str] = None
    description: Optional[str] = None
    viewport_x: Optional[float] = None
    viewport_y: Optional[float] = None
    viewport_zoom: Optional[float] = None
    nodes: Optional[List[NodeBase]] = None
    edges: Optional[List[EdgeBase]] = None


# Resolver forward referencias
TagWithMetrics.model_rebuild()
