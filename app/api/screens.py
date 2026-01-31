"""
CRUD de pantallas y layouts SCADA.
Maneja la persistencia de los diagramas de React Flow.
"""
import re
from typing import List, Union
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.db.session import get_session
from app.db.models import Screen
from app.schemas.scada import ScreenCreate, ScreenRead, ScreenUpdate, ScreenListItem

router = APIRouter(prefix="/screens", tags=["screens"])


def slugify(text: str) -> str:
    """
    Convierte un texto a slug URL-friendly.
    Ejemplo: "Main Screen" -> "main-screen"
    """
    # Convertir a minúsculas
    text = text.lower()
    # Reemplazar espacios y caracteres especiales con guiones
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    # Eliminar guiones múltiples
    text = re.sub(r'-+', '-', text)
    # Eliminar guiones al inicio y final
    text = text.strip('-')
    return text


@router.get("/", response_model=List[ScreenListItem])
async def list_screens(
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session)
):
    """
    Lista todas las pantallas SCADA disponibles.
    Devuelve versión ligera sin layout_data para optimizar la red.
    """
    stmt = select(Screen).offset(skip).limit(limit).order_by(Screen.name)
    result = await session.execute(stmt)
    screens = result.scalars().all()
    return screens


@router.post("/", response_model=ScreenRead, status_code=status.HTTP_201_CREATED)
async def create_screen(
    screen_data: ScreenCreate,
    session: AsyncSession = Depends(get_session)
):
    """
    Crea una nueva pantalla SCADA.
    
    - Si no se proporciona slug, se genera desde el nombre.
    - Si is_home=True, desactiva cualquier otra pantalla home existente.
    """
    # Generar slug si no viene
    slug = screen_data.slug or slugify(screen_data.name)
    
    # Verificar que el slug no exista
    existing = await session.execute(
        select(Screen).where(Screen.slug == slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una pantalla con slug '{slug}'"
        )
    
    # Verificar que el nombre no exista
    existing_name = await session.execute(
        select(Screen).where(Screen.name == screen_data.name)
    )
    if existing_name.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una pantalla con nombre '{screen_data.name}'"
        )
    
    # Si esta pantalla será home, desactivar la home actual
    if screen_data.is_home:
        await _clear_current_home(session)
    
    # Crear la pantalla
    screen = Screen(
        name=screen_data.name,
        slug=slug,
        description=screen_data.description,
        is_home=screen_data.is_home,
        layout_data=screen_data.layout_data
    )
    
    session.add(screen)
    await session.commit()
    await session.refresh(screen)
    
    return screen


@router.get("/home", response_model=ScreenRead)
async def get_home_screen(
    session: AsyncSession = Depends(get_session)
):
    """
    Obtiene la pantalla marcada como home.
    Útil para cargar el dashboard principal automáticamente.
    """
    result = await session.execute(
        select(Screen).where(Screen.is_home == True)
    )
    screen = result.scalar_one_or_none()
    
    if not screen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay pantalla home configurada"
        )
    
    return screen


@router.get("/{slug_or_id}", response_model=ScreenRead)
async def get_screen(
    slug_or_id: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Obtiene una pantalla específica con todos sus nodos y edges.
    Acepta tanto slug como ID numérico.
    """
    screen = await _get_screen_by_slug_or_id(session, slug_or_id)
    
    if not screen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pantalla '{slug_or_id}' no encontrada"
        )
    
    return screen


@router.put("/{screen_id}", response_model=ScreenRead)
async def update_screen(
    screen_id: int,
    screen_data: ScreenUpdate,
    session: AsyncSession = Depends(get_session)
):
    """
    Actualiza una pantalla existente (nodos, edges, layout, metadatos).
    """
    # Buscar la pantalla
    result = await session.execute(
        select(Screen).where(Screen.id == screen_id)
    )
    screen = result.scalar_one_or_none()
    
    if not screen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pantalla con ID {screen_id} no encontrada"
        )
    
    # Verificar slug único si se está cambiando
    if screen_data.slug and screen_data.slug != screen.slug:
        existing = await session.execute(
            select(Screen).where(
                Screen.slug == screen_data.slug,
                Screen.id != screen_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe una pantalla con slug '{screen_data.slug}'"
            )
    
    # Verificar nombre único si se está cambiando
    if screen_data.name and screen_data.name != screen.name:
        existing = await session.execute(
            select(Screen).where(
                Screen.name == screen_data.name,
                Screen.id != screen_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe una pantalla con nombre '{screen_data.name}'"
            )
    
    # Si se está marcando como home, desactivar la home actual
    if screen_data.is_home is True and not screen.is_home:
        await _clear_current_home(session, exclude_id=screen_id)
    
    # Actualizar campos proporcionados
    update_data = screen_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(screen, field, value)
    
    await session.commit()
    await session.refresh(screen)
    
    return screen


@router.delete("/{screen_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_screen(
    screen_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Elimina una pantalla SCADA.
    """
    result = await session.execute(
        select(Screen).where(Screen.id == screen_id)
    )
    screen = result.scalar_one_or_none()
    
    if not screen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pantalla con ID {screen_id} no encontrada"
        )
    
    await session.delete(screen)
    await session.commit()
    
    return None


# ============ Helper Functions ============

async def _clear_current_home(
    session: AsyncSession, 
    exclude_id: int = None
):
    """
    Desactiva la pantalla home actual (solo puede haber una).
    """
    stmt = select(Screen).where(Screen.is_home == True)
    if exclude_id:
        stmt = stmt.where(Screen.id != exclude_id)
    
    result = await session.execute(stmt)
    current_home = result.scalar_one_or_none()
    
    if current_home:
        current_home.is_home = False
        await session.flush()


async def _get_screen_by_slug_or_id(
    session: AsyncSession, 
    slug_or_id: str
) -> Screen | None:
    """
    Busca una pantalla por slug o ID.
    """
    # Intentar como ID numérico primero
    if slug_or_id.isdigit():
        result = await session.execute(
            select(Screen).where(Screen.id == int(slug_or_id))
        )
        screen = result.scalar_one_or_none()
        if screen:
            return screen
    
    # Buscar por slug
    result = await session.execute(
        select(Screen).where(Screen.slug == slug_or_id)
    )
    return result.scalar_one_or_none()
