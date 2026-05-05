from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import JSON, PrimaryKeyConstraint, String as SAString
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from fastapi_users.db import SQLAlchemyBaseUserTable



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

class AlarmStatus(str, Enum):
    ACTIVE_UNACK = "ACTIVE_UNACK"
    ACTIVE_ACK = "ACTIVE_ACK"
    CLEARED_UNACK = "CLEARED_UNACK" 
    CLEARED_ACK = "CLEARED_ACK"
    RESOLVED = "RESOLVED" 

class ScreenAccessRole(str, Enum):
    VIEWER = "VIEWER"
    EDITOR = "EDITOR"

class DataType(str, Enum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"

class AccessMode(str, Enum):
    READ = "R"
    WRITE = "W"
    READ_WRITE = "RW"



class User(SQLModel, table=True):
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    
    email: str = Field(unique=True, index=True, max_length=320)
    hashed_password: str = Field(max_length=1024)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    
    
    username: str = Field(unique=True, index=True)
    role: str = Field(default="OPERATOR") 
    full_name: Optional[str] = None



class Tag(SQLModel, table=True):
    """
    Catálogo maestro de variables.
    Soporta el patrón 'Protocol Factory' mediante 'connection_config'.
    """
    __tablename__ = "tags"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True) 
    description: Optional[str] = None
    unit: Optional[str] = None
    
    
    source_protocol: ProtocolType = Field(default=ProtocolType.SIMULATED)
    
    
    connection_config: Dict = Field(default={}, sa_column=Column(JSONB)) 
    
    scan_rate_ms: int = Field(default=1000) 
    mqtt_topic: str 
    
    is_enabled: bool = Field(default=True)
    
    
    data_type: str = Field(
        default="float",
        sa_column=Column(SAString, nullable=False, server_default="float")
    )
    access_mode: str = Field(
        default="R",
        sa_column=Column(SAString, nullable=False, server_default="R")
    )
    
    
    owner_id: Optional[int] = Field(default=None, foreign_key="users.id")
    
    
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
    quality: int = Field(default=192) 

    tag: Optional[Tag] = Relationship(back_populates="metrics")


class Screen(SQLModel, table=True):
    """
    Almacena el layout completo de React Flow en un JSON.
    Eliminamos las tablas Node y Edge para simplificar.
    """
    __tablename__ = "screens"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    slug: str = Field(unique=True, index=True) 
    description: Optional[str] = None
    
    
    layout_data: Dict = Field(default={}, sa_column=Column(JSONB)) 
    
    is_home: bool = Field(default=False)
    
    
    owner_id: Optional[int] = Field(default=None, foreign_key="users.id")

class ScreenAccess(SQLModel, table=True):
    """
    Tabla intermedia para gestionar con quién se comparten las pantallas.
    """
    __tablename__ = "screen_access"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    screen_id: int = Field(foreign_key="screens.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    role: ScreenAccessRole = Field(default=ScreenAccessRole.VIEWER)




class AlarmDefinition(SQLModel, table=True):
    __tablename__ = "alarm_definitions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    tag_id: int = Field(foreign_key="tags.id", unique=True)
    
    severity: AlarmSeverity = Field(default=AlarmSeverity.WARNING)
    message: str
    
    
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
    status: str = Field(default="ACTIVE_UNACK") 
    
    definition: Optional[AlarmDefinition] = Relationship(back_populates="events")