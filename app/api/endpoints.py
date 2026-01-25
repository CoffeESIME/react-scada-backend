"""
Rutas generales de la API SCADA.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["general"])


@router.get("/health")
async def health_check():
    """Endpoint de salud del sistema."""
    return {"status": "healthy", "service": "scada-backend"}


@router.get("/tags")
async def get_all_tags(session: AsyncSession = Depends(get_session)):
    """Obtiene todos los tags registrados en el sistema."""
    # TODO: Implementar query a la base de datos
    return {"tags": []}


@router.get("/tags/{tag_id}")
async def get_tag(tag_id: int, session: AsyncSession = Depends(get_session)):
    """Obtiene un tag específico por su ID."""
    # TODO: Implementar query a la base de datos
    raise HTTPException(status_code=404, detail="Tag not found")


@router.get("/metrics/{tag_id}")
async def get_tag_metrics(
    tag_id: int,
    limit: int = 100,
    session: AsyncSession = Depends(get_session)
):
    """Obtiene las métricas históricas de un tag."""
    # TODO: Implementar query a TimescaleDB
    return {"tag_id": tag_id, "metrics": []}
