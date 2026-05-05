"""
Rutas de autenticación usando FastAPI Users.
Proporciona endpoints para registro, login, logout y perfil.
"""
from fastapi import APIRouter

from app.users import fastapi_users, auth_backend, current_active_user
from app.schemas.user import UserCreate, UserRead, UserUpdate


router = APIRouter(tags=["authentication"])


router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
)


router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
)


router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
)
