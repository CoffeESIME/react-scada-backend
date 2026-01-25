"""
Rutas de autenticación: Login, Registro, Logout.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """
    Registra un nuevo usuario en el sistema.
    """
    # TODO: Implementar con FastAPI Users
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Registration not implemented yet"
    )


@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Autentica un usuario y retorna un token JWT.
    """
    # TODO: Implementar con FastAPI Users
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Login not implemented yet"
    )


@router.post("/logout")
async def logout():
    """
    Cierra la sesión del usuario actual.
    """
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserRead)
async def get_current_user():
    """
    Retorna información del usuario autenticado.
    """
    # TODO: Implementar con FastAPI Users
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated"
    )
