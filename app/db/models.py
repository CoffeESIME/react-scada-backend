from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import JSON, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from fastapi_users.db import SQLAlchemyBaseUserTable

# ============ Enums (Mantenemos los tuyos, son buenos) ============

class AlarmSeverity(int, Enum):
    """Usamos Int para poder ordenar por gravedad (3 > 1)"""
    INFO = 1
    WARNING = 2
    CRITICAL = 3

class ProtocolType(str, Enum):
    MODBUS = "modbus"
    OPCUA = "opcua"
    MQTT = "mqtt"
    SIMULATED = "simulated"

# ============ User Model ============

class User(SQLModel, table=True):
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # --- FastAPI Users Required Fields ---
    email: str = Field(unique=True, index=True, max_length=320)
    hashed_password: str = Field(max_length=1024)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    
    # --- Custom Fields ---
    username: str = Field(unique=True, index=True)
    role: str = Field(default="OPERATOR") # ADMIN, OPERATOR
    full_name: Optional[str] = None

# ============ SCADA Core Models ============

class Tag(SQLModel, table=True):
    """
    Catálogo maestro de variables.
    Soporta el patrón 'Protocol Factory' mediante 'connection_config'.
    """
    __tablename__ = "tags"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True) # Ej: "Tanque1_Nivel"
    description: Optional[str] = None
    unit: Optional[str] = None
    
    # --- Configuración del Protocol Factory ---
    source_protocol: ProtocolType = Field(default=ProtocolType.SIMULATED)
    
    # Guardamos la config compleja (IP, Reg, NodeID) en JSON
    connection_config: Dict = Field(default={}, sa_column=Column(JSONB)) 
    
    scan_rate_ms: int = Field(default=1000) # Frecuencia de lectura
    mqtt_topic: str # Topic normalizado: "scada/tags/tanque1"
    
    is_enabled: bool = Field(default=True)
    
    # Relaciones
    metrics: List["Metric"] = Relationship(back_populates="tag")
    alarm_definition: Optional["AlarmDefinition"] = Relationship(back_populates="tag")


class Metric(SQLModel, table=True):
    """
    Hypertable de TimescaleDB.
    NOTA: No tiene ID único tradicional. Su PK es compuesta (time + tag_id).
    """
    __tablename__ = "metrics"
    __table_args__ = (
        PrimaryKeyConstraint("time", "tag_id"),
    )
    
    time: datetime = Field(
        sa_column=Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    )
    tag_id: int = Field(foreign_key="tags.id")
    value: float
    quality: int = Field(default=192) # OPC UA Good

    tag: Optional[Tag] = Relationship(back_populates="metrics")


class Screen(SQLModel, table=True):
    """
    Almacena el layout completo de React Flow en un JSON.
    Eliminamos las tablas Node y Edge para simplificar.
    """
    __tablename__ = "screens"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    slug: str = Field(unique=True, index=True) # Para la URL /screen/main
    description: Optional[str] = None
    
    # Aquí vive todo el grafo de React Flow
    layout_data: Dict = Field(default={}, sa_column=Column(JSONB)) 
    
    is_home: bool = Field(default=False)


# ============ Alarm Models ============

class AlarmDefinition(SQLModel, table=True):
    __tablename__ = "alarm_definitions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    tag_id: int = Field(foreign_key="tags.id", unique=True)
    
    severity: AlarmSeverity = Field(default=AlarmSeverity.WARNING)
    message: str
    
    # Umbrales: {"HH": 90, "L": 10}
    limits: Dict = Field(default={}, sa_column=Column(JSONB))
    deadband: float = Field(default=0.0)
    
    is_active: bool = Field(default=True)
    
    tag: Optional[Tag] = Relationship(back_populates="alarm_definition")
    events: List["AlarmEvent"] = Relationship(back_populates="definition")


class AlarmEvent(SQLModel, table=True):
    __tablename__ = "alarm_events"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    definition_id: int = Field(foreign_key="alarm_definitions.id")
    
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    
    ack_time: Optional[datetime] = None
    ack_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    
    trigger_value: float
    status: str = Field(default="ACTIVE_UNACK") # Enum controlado por lógica
    
    definition: Optional[AlarmDefinition] = Relationship(back_populates="events")