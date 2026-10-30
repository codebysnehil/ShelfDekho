from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db import get_session
from app.schemas import (
    BreakdownResponse,
    MatrixResponse,
    ProductsResponse,
    SummaryResponse,
    TrendResponse,
    UpcomingResponse,
)
from app.services import dashboard

router = APIRouter(
    prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(require_user)]
)

# Periods are capped below a year so the current and last-year windows never overlap.
Days = Query(28, ge=7, le=364, description="Length of the period ending on the latest data date")
StoreId = Query(None, description="Limit to one store; omit for the whole chain")


@router.get("/summary", response_model=SummaryResponse)
async def summary(
    days: int = Days,
    store_id: int | None = StoreId,
    session: AsyncSession = Depends(get_session),
) -> SummaryResponse:
    """Headline KPIs vs last year plus auto-generated insights."""
    return await dashboard.summary(session, days, store_id)


@router.get("/trend", response_model=TrendResponse)
async def trend(
    weeks: int = Query(26, ge=4, le=52),
    store_id: int | None = StoreId,
    session: AsyncSession = Depends(get_session),
) -> TrendResponse:
    """Weekly revenue with the same week last year."""
    return await dashboard.trend(session, weeks, store_id)


@router.get("/breakdown", response_model=BreakdownResponse)
async def breakdown(
    dimension: Literal["store", "category"] = "category",
    days: int = Days,
    store_id: int | None = StoreId,
    session: AsyncSession = Depends(get_session),
) -> BreakdownResponse:
    as_of = await dashboard.data_as_of(session)
    period = dashboard.period_ending(as_of, days)
    return await dashboard.breakdown(session, dimension, period, store_id)


@router.get("/matrix", response_model=MatrixResponse)
async def matrix(days: int = Days, session: AsyncSession = Depends(get_session)) -> MatrixResponse:
    """Revenue change vs last year for every store x category."""
    as_of = await dashboard.data_as_of(session)
    return await dashboard.matrix(session, dashboard.period_ending(as_of, days))


@router.get("/upcoming", response_model=UpcomingResponse)
async def upcoming(
    days: int = Query(14, ge=1, le=56),
    limit: int = Query(6, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
) -> UpcomingResponse:
    """The next festival and the promotions starting in the coming days."""
    return await dashboard.upcoming(session, days, limit)


@router.get("/products", response_model=ProductsResponse)
async def products(
    sort: Literal["top", "declining"] = "top",
    days: int = Days,
    store_id: int | None = StoreId,
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> ProductsResponse:
    as_of = await dashboard.data_as_of(session)
    period = dashboard.period_ending(as_of, days)
    return await dashboard.products(session, sort, period, store_id, limit)
