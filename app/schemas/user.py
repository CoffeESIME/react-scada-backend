"""
Pydantic Schemas para validación de datos de Usuario.
Usando las clases base de FastAPI Users.
"""
from datetime import datetime
from typing import Optional

from fastapi_users import schemas


class UserRead(schemas.BaseUser[int]):
    """Schema de respuesta para usuario."""
    username: str
    role: str
    full_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UserCreate(schemas.BaseUserCreate):
    """Schema para crear un nuevo usuario."""
    username: str
    role: Optional[str] = "OPERATOR"
    full_name: Optional[str] = None


class UserUpdate(schemas.BaseUserUpdate):
    """Schema para actualizar un usuario."""
    username: Optional[str] = None
    role: Optional[str] = None
    full_name: Optional[str] = None
