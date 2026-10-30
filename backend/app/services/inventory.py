"""Stock health: combines on-hand inventory with next week's demand forecast."""

import datetime as dt

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import (
    AlertCounts,
    AlertRow,
    AlertsResponse,
    ForecastPoint,
    ForecastSeries,
    ProductOut,
    StoreOut,
)

OVERSTOCK_DAYS = 60
MIN_DAILY_DEMAND = 0.05


def classify(on_hand: int, daily_demand: float, lead_time_days: int) -> tuple[float | None, str]:
    """Days of cover and a status. Stock-out risk means stock runs out before a
    replenishment order placed today could arrive."""
    if daily_demand < MIN_DAILY_DEMAND:
        return None, "overstock" if on_hand > 0 else "healthy"
    cover = on_hand / daily_demand
    if cover < lead_time_days:
        return cover, "stockout_risk"
    if cover > OVERSTOCK_DAYS:
        return cover, "overstock"
    return cover, "healthy"


async def alerts(
    session: AsyncSession, *, store_id: int | None, status: str | None, limit: int
) -> AlertsResponse:
    rows = (
        await session.execute(
            text(
                """
                WITH nxt AS (
                  SELECT store_id, product_id, units
                  FROM forecasts
                  WHERE week_start = (SELECT MIN(week_start) FROM forecasts)
                )
                SELECT s.id AS store_id, s.name || ', ' || s.city AS store_name,
                       p.id AS product_id, p.sku, p.name AS product_name, p.category,
                       p.unit_price, p.lead_time_days, i.on_hand, i.as_of,
                       nxt.units / 7.0 AS daily_demand
                FROM inventory i
                JOIN stores s ON s.id = i.store_id
                JOIN products p ON p.id = i.product_id
                JOIN nxt ON nxt.store_id = i.store_id AND nxt.product_id = i.product_id
                WHERE CAST(:store_id AS integer) IS NULL OR i.store_id = CAST(:store_id AS integer)
                """
            ),
            {"store_id": store_id},
        )
    ).all()

    built: list[AlertRow] = []
    for r in rows:
        demand = float(r.daily_demand)
        cover, row_status = classify(r.on_hand, demand, r.lead_time_days)
        shortfall = max(0.0, demand * r.lead_time_days - r.on_hand)
        built.append(
            AlertRow(
                store_id=r.store_id,
                store_name=r.store_name,
                product_id=r.product_id,
                sku=r.sku,
                product_name=r.product_name,
                category=r.category,
                on_hand=r.on_hand,
                daily_demand=round(demand, 2),
                days_of_cover=None if cover is None else round(cover, 1),
                lead_time_days=r.lead_time_days,
                status=row_status,  # type: ignore[arg-type]
                revenue_at_risk=round(shortfall * float(r.unit_price)),
                unit_price=float(r.unit_price),
            )
        )

    counts = AlertCounts(
        stockout_risk=sum(a.status == "stockout_risk" for a in built),
        overstock=sum(a.status == "overstock" for a in built),
        healthy=sum(a.status == "healthy" for a in built),
    )
    at_risk = sum(a.revenue_at_risk for a in built)
    selected = [a for a in built if status is None or a.status == status]
    if status == "overstock":
        selected.sort(key=lambda a: a.days_of_cover or float("inf"), reverse=True)
    else:
        selected.sort(key=lambda a: a.revenue_at_risk, reverse=True)

    as_of = max((r.as_of for r in rows), default=dt.date.today())
    return AlertsResponse(
        as_of=as_of, counts=counts, revenue_at_risk=at_risk, rows=selected[:limit]
    )


async def series(
    session: AsyncSession, store_id: int, product_id: int, history_weeks: int
) -> ForecastSeries | None:
    head = (
        await session.execute(
            text(
                """
                SELECT s.id AS s_id, s.code, s.name AS s_name, s.city, s.region, s.format,
                       p.id AS p_id, p.sku, p.name AS p_name, p.category, p.unit_price,
                       p.lead_time_days, i.on_hand
                FROM stores s CROSS JOIN products p
                JOIN inventory i ON i.store_id = s.id AND i.product_id = p.id
                WHERE s.id = :store_id AND p.id = :product_id
                """
            ),
            {"store_id": store_id, "product_id": product_id},
        )
    ).one_or_none()
    if head is None:
        return None

    points = (
        await session.execute(
            text(
                """
                WITH hist AS (
                  SELECT date_trunc('week', sale_date)::date AS wk, SUM(units) AS units
                  FROM daily_sales
                  WHERE store_id = :store_id AND product_id = :product_id
                    AND sale_date > (SELECT MAX(sale_date) FROM daily_sales) - CAST(:days AS integer)
                  GROUP BY 1
                ),
                fc AS (
                  SELECT week_start AS wk, units, lower, upper
                  FROM forecasts WHERE store_id = :store_id AND product_id = :product_id
                ),
                promo AS (
                  SELECT DISTINCT w.wk
                  FROM promotions pr
                  CROSS JOIN LATERAL (
                    SELECT gs::date AS wk
                    FROM generate_series(date_trunc('week', pr.start_date), pr.end_date,
                                         interval '1 week') gs
                  ) w
                  WHERE pr.product_id = :product_id
                )
                SELECT COALESCE(h.wk, f.wk) AS wk, h.units AS actual, f.units AS forecast,
                       f.lower, f.upper, (pm.wk IS NOT NULL) AS on_promo
                FROM hist h
                FULL OUTER JOIN fc f ON f.wk = h.wk
                LEFT JOIN promo pm ON pm.wk = COALESCE(h.wk, f.wk)
                ORDER BY 1
                """
            ),
            {"store_id": store_id, "product_id": product_id, "days": history_weeks * 7},
        )
    ).all()

    next_week = next((p.forecast for p in points if p.forecast is not None), None)
    demand = (next_week or 0.0) / 7
    cover, row_status = classify(head.on_hand, demand, head.lead_time_days)
    return ForecastSeries(
        store=StoreOut(
            id=head.s_id,
            code=head.code,
            name=head.s_name,
            city=head.city,
            region=head.region,
            format=head.format,
        ),
        product=ProductOut(
            id=head.p_id,
            sku=head.sku,
            name=head.p_name,
            category=head.category,
            unit_price=float(head.unit_price),
            lead_time_days=head.lead_time_days,
        ),
        on_hand=head.on_hand,
        days_of_cover=None if cover is None else round(cover, 1),
        status=row_status,  # type: ignore[arg-type]
        points=[
            ForecastPoint(
                week_start=p.wk,
                # A week with a forecast is still in progress, so its sales so far would mislead.
                actual=None if p.actual is None or p.forecast is not None else float(p.actual),
                forecast=None if p.forecast is None else round(p.forecast, 1),
                lower=None if p.lower is None else round(p.lower, 1),
                upper=None if p.upper is None else round(p.upper, 1),
                on_promo=bool(p.on_promo),
            )
            for p in points
        ],
    )
