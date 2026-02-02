from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc
from typing import List, Optional
from datetime import datetime, timedelta

from app.db.session import get_session
from app.db.models import Metric, Tag

router = APIRouter()

@router.get("/history", response_model=List[dict])
async def get_history(
    tag_ids: str = Query(..., description="Comma-separated tag IDs (e.g. '1,2,3')"),
    start: datetime = Query(..., description="Start timestamp (ISO 8601)"),
    end: datetime = Query(..., description="End timestamp (ISO 8601)"),
    session: AsyncSession = Depends(get_session)
):
    """
    Fetch historical data for multiple tags within a time range.
    Returns a list of data series formatted for frontend charts.
    """
    tag_id_list = [int(tid.strip()) for tid in tag_ids.split(",") if tid.strip().isdigit()]
    
    if not tag_id_list:
        return []

    # Query metrics
    # Optimización: En TimescaleDB, siempre filtrar por tiempo primero.
    query = (
        select(Metric)
        .where(Metric.time >= start)
        .where(Metric.time <= end)
        .where(Metric.tag_id.in_(tag_id_list))
        .order_by(Metric.time.asc())
    )

    result = await session.execute(query)
    metrics = result.scalars().all()

    # Agrupar por Tag ID para facilitar el consumo del frontend
    # Formato de retorno: 
    # [
    #   { 
    #     tagId: 1, 
    #     data: [{x: timestamp, y: value}, ...] 
    #   },
    #   ...
    # ]
    
    grouped_data = {tid: [] for tid in tag_id_list}
    
    for m in metrics:
        if m.tag_id in grouped_data:
            grouped_data[m.tag_id].append({
                "x": m.time.isoformat(),
                "y": m.value
            })

    response = [
        {"tagId": tid, "data": data}
        for tid, data in grouped_data.items()
    ]

    return response

@router.get("/history/latest/{tag_id}")
async def get_latest_history(
    tag_id: int,
    limit: int = 50,
    session: AsyncSession = Depends(get_session)
):
    """
    Fetch the latest N records for a specific tag.
    Returns data in chronological order (oldest to newest) for charting.
    """
    # 1. Query latest records (descending time)
    query = (
        select(Metric)
        .where(Metric.tag_id == tag_id)
        .order_by(desc(Metric.time))
        .limit(limit)
    )
    
    result = await session.execute(query)
    metrics = result.scalars().all()
    
    # 2. Reverse to get chronological order (past -> present)
    metrics = list(metrics)
    metrics.reverse()
    
    # 3. Format result
    data = [{
        "x": m.time.isoformat(),
        "y": m.value
    } for m in metrics]

    return {
        "tagId": tag_id,
        "data": data
    }
