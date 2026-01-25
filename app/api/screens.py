"""
CRUD de pantallas y layouts SCADA.
Maneja la persistencia de los diagramas de React Flow.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.scada import ScreenCreate, ScreenRead, ScreenUpdate

router = APIRouter(prefix="/screens", tags=["screens"])


@router.get("/", response_model=List[ScreenRead])
async def list_screens(
    skip: int = 0,
    limit: int = 20,
    session: AsyncSession = Depends(get_session)
):
    """
    Lista todas las pantallas SCADA disponibles.
    """
    # TODO: Implementar query a la base de datos
    return []


@router.post("/", response_model=ScreenRead, status_code=status.HTTP_201_CREATED)
async def create_screen(
    screen_data: ScreenCreate,
    session: AsyncSession = Depends(get_session)
):
    """
    Crea una nueva pantalla SCADA.
    """
    # TODO: Implementar creación en base de datos
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Screen creation not implemented yet"
    )


@router.get("/{screen_id}", response_model=ScreenRead)
async def get_screen(
    screen_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Obtiene una pantalla específica con todos sus nodos y edges.
    """
    # TODO: Implementar query a la base de datos
    raise HTTPException(status_code=404, detail="Screen not found")


@router.put("/{screen_id}", response_model=ScreenRead)
async def update_screen(
    screen_id: int,
    screen_data: ScreenUpdate,
    session: AsyncSession = Depends(get_session)
):
    """
    Actualiza una pantalla existente (nodos, edges, layout).
    """
    # TODO: Implementar actualización en base de datos
    raise HTTPException(status_code=404, detail="Screen not found")


@router.delete("/{screen_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_screen(
    screen_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Elimina una pantalla SCADA.
    """
    # TODO: Implementar eliminación en base de datos
    raise HTTPException(status_code=404, detail="Screen not found")
