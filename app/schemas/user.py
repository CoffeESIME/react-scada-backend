"""
Pydantic Schemas para validación de datos de Usuario.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Campos comunes del usuario."""
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=255)


class UserCreate(UserBase):
    """Schema para crear un nuevo usuario."""
    password: str = Field(..., min_length=8, max_length=100)


class UserUpdate(BaseModel):
    """Schema para actualizar un usuario."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, min_length=8, max_length=100)
    is_active: Optional[bool] = None


class UserRead(UserBase):
    """Schema de respuesta para usuario."""
    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """Schema para login."""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Schema de respuesta de token JWT."""
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Payload del token JWT."""
    sub: int  # user_id
    exp: datetime
