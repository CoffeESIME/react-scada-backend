"""
Pydantic Schemas para validación de datos de Usuario.
Usando las clases base de FastAPI Users.
"""
from datetime import datetime
from typing import Optional

from fastapi_users import schemas


class UserRead(schemas.BaseUser[int]):
    """Schema de respuesta para usuario."""
    full_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UserCreate(schemas.BaseUserCreate):
    """Schema para crear un nuevo usuario."""
    full_name: Optional[str] = None


class UserUpdate(schemas.BaseUserUpdate):
    """Schema para actualizar un usuario."""
    full_name: Optional[str] = None
