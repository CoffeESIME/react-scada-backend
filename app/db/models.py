"""
Definición de Tablas de la Base de Datos.
Usando SQLModel (SQLAlchemy + Pydantic).
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Any
from uuid import UUID, uuid4

from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import JSON, Text


# ============ Enums ============

class AlarmSeverity(str, Enum):
    """Niveles de severidad de alarmas."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlarmStatus(str, Enum):
    """Estado de una alarma."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class TagDataType(str, Enum):
    """Tipos de datos soportados para tags."""
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"


class NodeType(str, Enum):
    """Tipos de nodos SCADA disponibles."""
    MOTOR = "motor"
    VALVE = "valve"
    TANK = "tank"
    GAUGE = "gauge"
    PUMP = "pump"
    SENSOR = "sensor"
    PLC = "plc"
    LABEL = "label"


# ============ User Model ============

class User(SQLModel, table=True):
    """Modelo de Usuario para autenticación."""
    
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    hashed_password: str = Field(max_length=255)
    full_name: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============ SCADA Core Models ============

class Tag(SQLModel, table=True):
    """
    Tag SCADA: representa un punto de datos del proceso.
    Puede estar asociado a un dispositivo Modbus, OPC-UA, o MQTT.
    """
    
    __tablename__ = "tags"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=100)  # Ej: "motor_01_speed"
    description: Optional[str] = Field(default=None, max_length=500)
    data_type: TagDataType = Field(default=TagDataType.FLOAT)
    unit: Optional[str] = Field(default=None, max_length=50)  # Ej: "RPM", "°C", "PSI"
    
    # Límites para alarmas
    low_limit: Optional[float] = Field(default=None)
    high_limit: Optional[float] = Field(default=None)
    low_low_limit: Optional[float] = Field(default=None)
    high_high_limit: Optional[float] = Field(default=None)
    
    # Origen del dato
    source_type: str = Field(default="mqtt", max_length=50)  # mqtt, modbus, opcua
    source_address: Optional[str] = Field(default=None, max_length=255)  # Topic o dirección
    
    # Valor actual (cache)
    current_value: Optional[str] = Field(default=None)
    last_updated: Optional[datetime] = Field(default=None)
    
    # Relaciones
    metrics: List["Metric"] = Relationship(back_populates="tag")
    alarms: List["Alarm"] = Relationship(back_populates="tag")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Metric(SQLModel, table=True):
    """
    Métrica histórica: valor de un tag en un momento específico.
    Esta tabla será convertida a Hypertable en TimescaleDB.
    """
    
    __tablename__ = "metrics"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    tag_id: int = Field(foreign_key="tags.id", index=True)
    value: float = Field(...)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    quality: int = Field(default=192)  # OPC-UA quality code (192 = Good)
    
    # Relación
    tag: Optional[Tag] = Relationship(back_populates="metrics")


class Alarm(SQLModel, table=True):
    """
    Alarma del sistema SCADA.
    Se genera cuando un tag cruza sus límites configurados.
    """
    
    __tablename__ = "alarms"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    tag_id: Optional[int] = Field(default=None, foreign_key="tags.id", index=True)
    
    severity: AlarmSeverity = Field(default=AlarmSeverity.WARNING)
    status: AlarmStatus = Field(default=AlarmStatus.ACTIVE)
    message: str = Field(max_length=500)
    
    triggered_value: Optional[float] = Field(default=None)
    trigger_condition: Optional[str] = Field(default=None, max_length=100)  # Ej: "> high_limit"
    
    triggered_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    acknowledged_at: Optional[datetime] = Field(default=None)
    acknowledged_by: Optional[int] = Field(default=None, foreign_key="users.id")
    resolved_at: Optional[datetime] = Field(default=None)
    
    # Relación
    tag: Optional[Tag] = Relationship(back_populates="alarms")


# ============ Screen/Layout Models ============

class Screen(SQLModel, table=True):
    """
    Pantalla SCADA: contenedor de nodos y conexiones.
    Representa un layout de React Flow guardado.
    """
    
    __tablename__ = "screens"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    thumbnail_url: Optional[str] = Field(default=None, max_length=500)
    
    # Configuración del viewport
    viewport_x: float = Field(default=0)
    viewport_y: float = Field(default=0)
    viewport_zoom: float = Field(default=1)
    
    # Metadata
    is_default: bool = Field(default=False)
    created_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relaciones
    nodes: List["Node"] = Relationship(back_populates="screen")
    edges: List["Edge"] = Relationship(back_populates="screen")


class Node(SQLModel, table=True):
    """
    Nodo de React Flow: representa un widget SCADA en el canvas.
    """
    
    __tablename__ = "nodes"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    node_id: str = Field(index=True, max_length=100)  # ID de React Flow
    screen_id: int = Field(foreign_key="screens.id", index=True)
    
    node_type: NodeType = Field(default=NodeType.GAUGE)
    label: Optional[str] = Field(default=None, max_length=100)
    
    # Posición en el canvas
    position_x: float = Field(default=0)
    position_y: float = Field(default=0)
    width: Optional[float] = Field(default=None)
    height: Optional[float] = Field(default=None)
    
    # Tag asociado (para mostrar datos en tiempo real)
    tag_id: Optional[int] = Field(default=None, foreign_key="tags.id")
    
    # Configuración específica del widget (JSON)
    config: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Relación
    screen: Optional[Screen] = Relationship(back_populates="nodes")


class Edge(SQLModel, table=True):
    """
    Edge de React Flow: conexión entre nodos.
    """
    
    __tablename__ = "edges"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    edge_id: str = Field(index=True, max_length=100)  # ID de React Flow
    screen_id: int = Field(foreign_key="screens.id", index=True)
    
    source_node_id: str = Field(max_length=100)
    target_node_id: str = Field(max_length=100)
    source_handle: Optional[str] = Field(default=None, max_length=50)
    target_handle: Optional[str] = Field(default=None, max_length=50)
    
    # Estilo
    edge_type: str = Field(default="default", max_length=50)  # Ej: "smoothstep", "straight"
    animated: bool = Field(default=False)
    style: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Relación
    screen: Optional[Screen] = Relationship(back_populates="edges")
