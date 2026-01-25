"""
Configuración de FastAPI Users para autenticación.
Maneja registro, login, y gestión de usuarios.
"""
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, IntegerIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from app.core.config import settings
from app.db.models import User
from app.db.session import get_session


# User Manager
class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    """Manager personalizado para usuarios."""
    
    reset_password_token_secret = settings.secret_key
    verification_token_secret = settings.secret_key
    
    async def on_after_register(
        self, user: User, request: Optional[Request] = None
    ):
        """Callback después de registro exitoso."""
        print(f"User {user.id} has registered.")
    
    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Callback para recuperación de contraseña."""
        print(f"User {user.id} has forgot their password. Token: {token}")


# Dependencia para obtener el User DB
async def get_user_db(session=Depends(get_session)):
    """Retorna la base de datos de usuarios."""
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(user_db=Depends(get_user_db)):
    """Retorna el manager de usuarios."""
    yield UserManager(user_db)


# Configuración de autenticación JWT
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    """Estrategia JWT para autenticación."""
    return JWTStrategy(
        secret=settings.secret_key,
        lifetime_seconds=settings.access_token_expire_minutes * 60
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# FastAPI Users instance
fastapi_users = FastAPIUsers[User, int](
    get_user_manager,
    [auth_backend],
)

# Dependencias comunes
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
