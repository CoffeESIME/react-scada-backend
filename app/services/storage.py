"""
Servicio para persistencia de métricas en TimescaleDB.
"""
from datetime import datetime
from app.db.session import async_session_factory
from app.db.models import Metric

async def save_metric(tag_id: int, value: float, quality: int = 192) -> bool:
    """
    Guarda una métrica en la base de datos (Hypertable).
    
    Args:
        tag_id: ID del Tag
        value: Valor numérico
        quality: Calidad OPC UA (Default 192 = Good)
    """
    try:
        async with async_session_factory() as session:
            metric = Metric(
                tag_id=tag_id,
                value=value,
                quality=quality,
                time=datetime.utcnow()
            )
            session.add(metric)
            await session.commit()
            return True
            
    except Exception as e:
        print(f"Error saving metric for tag {tag_id}: {e}")
        return False
