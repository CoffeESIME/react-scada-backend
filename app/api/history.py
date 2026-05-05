from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy import func

from app.db.session import get_session
from app.db.models import Metric, Tag, User
from app.users import current_active_user

router = APIRouter()

@router.get("/history", response_model=List[dict])
async def get_history(
    tag_ids: str = Query(..., description="Comma-separated tag IDs (e.g. '1,2,3')"),
    start: datetime = Query(..., description="Start timestamp (ISO 8601)"),
    end: datetime = Query(..., description="End timestamp (ISO 8601)"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user)
):
    """
    Fetch historical data for multiple tags within a time range.
    Returns a list of data series formatted for frontend charts.
    """
    tag_id_list = [int(tid.strip()) for tid in tag_ids.split(",") if tid.strip().isdigit()]
    
    if not tag_id_list:
        return []

    # Query tags to get names
    tag_query = select(Tag).where(Tag.id.in_(tag_id_list))
    tag_result = await session.execute(tag_query)
    tags_map = {tag.id: tag.name for tag in tag_result.scalars().all()}

    # Ensure start/end are timezone-aware (UTC) for correct comparison
    # against timestamptz columns in TimescaleDB
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    # Query metrics
    # Optimización: En TimescaleDB, siempre filtrar por tiempo primero.
    duration = end - start
    total_seconds = duration.total_seconds()
    
    # Target max 1000 points per series to prevent browser freeze
    max_points = 1000
    bucket_seconds = max(1, int(total_seconds / max_points))

    grouped_data = {tid: [] for tid in tag_id_list}

    if bucket_seconds > 1:
        # Downsampling with time_bucket
        time_bucket = func.time_bucket(timedelta(seconds=bucket_seconds), Metric.time).label("bucket")
        query = (
            select(
                time_bucket,
                Metric.tag_id,
                func.avg(Metric.value).label("value")
            )
            .where(Metric.time >= start)
            .where(Metric.time <= end)
            .where(Metric.tag_id.in_(tag_id_list))
            .group_by(Metric.tag_id, time_bucket)
            .order_by(time_bucket.asc())
        )
        
        result = await session.execute(query)
        metrics = result.all()
        
        for row in metrics:
            bucket, tag_id, value = row
            if tag_id in grouped_data:
                ts = bucket
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                else:
                    ts = ts.astimezone(timezone.utc)
                
                # Format to precision 4 for floats
                grouped_data[tag_id].append({
                    "x": ts.isoformat().replace("+00:00", "Z"),
                    "y": round(float(value), 4) if value is not None else 0
                })
    else:
        # Raw query for very small intervals (e.g. seconds)
        query = (
            select(Metric)
            .where(Metric.time >= start)
            .where(Metric.time <= end)
            .where(Metric.tag_id.in_(tag_id_list))
            .order_by(Metric.time.asc())
        )

        result = await session.execute(query)
        metrics = result.scalars().all()
        
        for m in metrics:
            if m.tag_id in grouped_data:
                # Ensure timestamp is always a valid UTC ISO-8601 string for the frontend.
                ts = m.time
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                else:
                    ts = ts.astimezone(timezone.utc)
                grouped_data[m.tag_id].append({
                    "x": ts.isoformat().replace("+00:00", "Z"),
                    "y": m.value
                })

    response = [
        {
            "tagId": tid, 
            "tagName": tags_map.get(tid, f"Tag {tid}"),
            "data": data
        }
        for tid, data in grouped_data.items()
    ]

    return response

@router.get("/history/latest/{tag_id}")
async def get_latest_history(
    tag_id: int,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user)
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
        "x": (m.time.astimezone(timezone.utc) if m.time.tzinfo else m.time.replace(tzinfo=timezone.utc)).isoformat().replace("+00:00", "Z"),
        "y": m.value
    } for m in metrics]

    return {
        "tagId": tag_id,
        "data": data
    }
