from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db import get_session
from app.models import ForecastRun
from app.schemas import AlertsResponse, ForecastMetrics, ForecastSeries
from app.services import inventory

router = APIRouter(prefix="/api/forecast", tags=["forecast"], dependencies=[Depends(require_user)])


@router.get("/metrics", response_model=ForecastMetrics)
async def metrics(session: AsyncSession = Depends(get_session)) -> ForecastMetrics:
    """Backtest accuracy of the latest forecast run against naive baselines."""
    run = await session.scalar(select(ForecastRun).order_by(ForecastRun.id.desc()).limit(1))
    if run is None:
        raise HTTPException(404, "No forecast run yet")
    baselines = {
        "naive (last week)": run.wape_naive,
        "4-week moving average": run.wape_moving_avg,
    }
    if run.wape_seasonal_naive is not None:
        baselines["seasonal naive (same week last year)"] = run.wape_seasonal_naive
    best_name, best_wape = min(baselines.items(), key=lambda kv: kv[1])
    return ForecastMetrics(
        created_at=run.created_at,
        series_count=run.series_count,
        horizon_weeks=run.horizon_weeks,
        backtest_weeks=run.backtest_weeks,
        wape_model=run.wape_model,
        wape_naive=run.wape_naive,
        wape_seasonal_naive=run.wape_seasonal_naive,
        wape_moving_avg=run.wape_moving_avg,
        best_baseline=best_name,
        improvement_pct=round((best_wape - run.wape_model) / best_wape * 100, 1),
    )


@router.get("/alerts", response_model=AlertsResponse)
async def alerts(
    status: Literal["stockout_risk", "overstock", "healthy", "all"] = "stockout_risk",
    store_id: int | None = None,
    limit: int = Query(25, ge=1, le=400),
    session: AsyncSession = Depends(get_session),
) -> AlertsResponse:
    """Store x SKU stock health from on-hand inventory and next week's forecast."""
    return await inventory.alerts(
        session, store_id=store_id, status=None if status == "all" else status, limit=limit
    )


@router.get("/series", response_model=ForecastSeries)
async def series(
    store_id: int,
    product_id: int,
    history_weeks: int = Query(26, ge=4, le=104),
    session: AsyncSession = Depends(get_session),
) -> ForecastSeries:
    """Weekly actuals followed by the forecast with an 80% interval."""
    result = await inventory.series(session, store_id, product_id, history_weeks)
    if result is None:
        raise HTTPException(404, "Unknown store or product")
    return result
