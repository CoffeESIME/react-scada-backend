"""
Rutas generales de la API SCADA.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

router = APIRouter(prefix="/v1", tags=["general"])


@router.get("/health")
async def health_check():
    """Endpoint de salud del sistema."""
    return {"status": "healthy", "service": "scada-backend"}


@router.get("/metrics/{tag_id}")
async def get_tag_metrics(
    tag_id: int,
    limit: int = 100,
    session: AsyncSession = Depends(get_session)
):
    """Obtiene las métricas históricas de un tag."""
    # TODO: Implementar query a TimescaleDB
    return {"tag_id": tag_id, "metrics": []}

