"""Sales analytics queries behind the overview dashboard.

Every metric is compared with the same period last year, shifted by 364 days so
weekdays line up (a Saturday is compared with a Saturday).
"""

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import (
    BreakdownResponse,
    BreakdownRow,
    ChartEvent,
    Insight,
    Kpi,
    MatrixCell,
    MatrixResponse,
    MatrixRow,
    ProductRow,
    ProductsResponse,
    SummaryResponse,
    TrendPoint,
    TrendResponse,
    UpcomingPromotion,
    UpcomingResponse,
)
from app.services import inventory
from app.services.calendar import DIWALI

LY = dt.timedelta(days=364)
STORE_FILTER = "(CAST(:store_id AS integer) IS NULL OR ds.store_id = CAST(:store_id AS integer))"


@dataclass(frozen=True)
class Period:
    start: dt.date
    end: dt.date

    @property
    def last_year(self) -> "Period":
        return Period(self.start - LY, self.end - LY)

    def params(self) -> dict:
        ly = self.last_year
        return {"start": self.start, "end": self.end, "ly_start": ly.start, "ly_end": ly.end}


async def data_as_of(session: AsyncSession) -> dt.date:
    """The latest day with figures from most of the chain. A file covering only some stores
    must not read as sales collapsing, so that day counts once the rest arrive."""
    as_of = await session.scalar(
        text(
            """
            WITH recent AS (
              SELECT sale_date, COUNT(*) AS n FROM daily_sales
              WHERE sale_date > (SELECT MAX(sale_date) FROM daily_sales) - 60
              GROUP BY 1
            )
            SELECT MAX(sale_date) FROM recent
            WHERE n >= 0.5 * (SELECT MAX(n) FROM recent)
            """
        )
    )
    if as_of is None:
        raise LookupError("no sales data loaded")
    return as_of


def period_ending(as_of: dt.date, days: int) -> Period:
    return Period(as_of - dt.timedelta(days=days - 1), as_of)


def format_inr(value: float) -> str:
    """Compact rupees in the Indian system: ₹8.4K, ₹20.7 L, ₹3.16 Cr."""
    if abs(value) >= 1e7:
        return f"₹{value / 1e7:.2f} Cr"
    if abs(value) >= 1e5:
        return f"₹{value / 1e5:.1f} L"
    if abs(value) >= 1e3:
        return f"₹{value / 1e3:.1f}K"
    return f"₹{value:.0f}"


def festive_run_up(period: Period) -> dt.date | None:
    """The Diwali whose two-week shopping run-up falls mostly inside the period, if any."""
    for diwali in DIWALI:
        run_up_start = diwali - dt.timedelta(days=14)
        overlap = (min(diwali, period.end) - max(run_up_start, period.start)).days + 1
        if overlap >= 7:
            return diwali
    return None


def pct_change(current: float, previous: float | None) -> float | None:
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


async def summary(session: AsyncSession, days: int, store_id: int | None) -> SummaryResponse:
    as_of = await data_as_of(session)
    period = period_ending(as_of, days)
    row = (
        await session.execute(
            text(
                f"""
                SELECT
                  COALESCE(SUM(revenue) FILTER (WHERE sale_date >= :start), 0) AS rev,
                  COALESCE(SUM(revenue) FILTER (WHERE sale_date <= :ly_end), 0) AS rev_ly,
                  COALESCE(SUM(units) FILTER (WHERE sale_date >= :start), 0) AS units,
                  COALESCE(SUM(units) FILTER (WHERE sale_date <= :ly_end), 0) AS units_ly,
                  COALESCE(SUM(cost) FILTER (WHERE sale_date >= :start), 0) AS cost,
                  COALESCE(SUM(cost) FILTER (WHERE sale_date <= :ly_end), 0) AS cost_ly,
                  COALESCE(SUM(revenue) FILTER (
                    WHERE sale_date >= :start AND promo_discount > 0), 0) AS promo,
                  COALESCE(SUM(revenue) FILTER (
                    WHERE sale_date <= :ly_end AND promo_discount > 0), 0) AS promo_ly
                FROM daily_sales ds
                WHERE {STORE_FILTER}
                  AND (sale_date BETWEEN :start AND :end OR sale_date BETWEEN :ly_start AND :ly_end)
                """
            ),
            {**period.params(), "store_id": store_id},
        )
    ).one()
    rev, rev_ly = float(row.rev), float(row.rev_ly)
    margin = (rev - float(row.cost)) / rev * 100 if rev else 0.0
    margin_ly = (rev_ly - float(row.cost_ly)) / rev_ly * 100 if rev_ly else None
    promo = float(row.promo) / rev * 100 if rev else 0.0
    promo_ly = float(row.promo_ly) / rev_ly * 100 if rev_ly else None

    def pts(current: float, previous: float | None) -> float | None:
        return None if previous is None else round(current - previous, 1)

    kpis = [
        Kpi(
            key="revenue",
            label="Revenue",
            value=round(rev),
            previous=round(rev_ly) or None,
            change_pct=pct_change(rev, rev_ly),
            unit="inr",
        ),
        Kpi(
            key="units",
            label="Units sold",
            value=int(row.units),
            previous=int(row.units_ly) or None,
            change_pct=pct_change(int(row.units), int(row.units_ly)),
            unit="units",
        ),
        # For percentage KPIs change_pct is the change in percentage points.
        Kpi(
            key="gross_margin",
            label="Gross margin",
            value=round(margin, 1),
            previous=None if margin_ly is None else round(margin_ly, 1),
            change_pct=pts(margin, margin_ly),
            unit="pct",
        ),
        Kpi(
            key="promo_share",
            label="Revenue on promotion",
            value=round(promo, 1),
            previous=None if promo_ly is None else round(promo_ly, 1),
            change_pct=pts(promo, promo_ly),
            unit="pct",
        ),
    ]

    insights = await _insights(session, period, store_id, kpis[0])
    return SummaryResponse(
        as_of=as_of, period_start=period.start, period_days=days, kpis=kpis, insights=insights
    )


async def _insights(
    session: AsyncSession, period: Period, store_id: int | None, revenue: Kpi
) -> list[Insight]:
    insights: list[Insight] = []

    alerts = await inventory.alerts(session, store_id=store_id, status=None, limit=1)
    if alerts.counts.stockout_risk:
        insights.append(
            Insight(
                kind="stockout",
                tone="negative",
                title=f"{alerts.counts.stockout_risk} SKUs at risk of stocking out",
                detail=(
                    f"{format_inr(alerts.revenue_at_risk)} of sales at risk before "
                    "replenishment can arrive."
                ),
            )
        )

    # Diwali moves by up to three weeks a year, which distorts year-over-year numbers.
    this_year, last_year = festive_run_up(period), festive_run_up(period.last_year)
    if (this_year is None) != (last_year is None):
        insights.append(
            Insight(
                kind="festival",
                tone="neutral",
                title="Diwali timing distorts this comparison",
                detail=(
                    f"Last year's period includes the Diwali run-up ({last_year:%d %b %Y}); "
                    "this year's does not."
                    if last_year
                    else f"This period includes the Diwali run-up ({this_year:%d %b %Y}); "
                    "last year's did not."
                ),
            )
        )

    categories = await breakdown(session, "category", period, store_id)
    ranked = sorted(
        (r for r in categories.rows if r.yoy_pct is not None), key=lambda r: r.yoy_pct or 0
    )
    if ranked:
        best = ranked[-1]
        insights.append(
            Insight(
                kind="category",
                tone="positive" if (best.yoy_pct or 0) > 0 else "neutral",
                title=f"{best.name} is the fastest-growing category",
                detail=f"{best.yoy_pct:+.1f}% vs last year, {best.share_pct:.0f}% of revenue.",
            )
        )

    if store_id is None:
        stores = await breakdown(session, "store", period, None)
        ranked_stores = sorted(
            (r for r in stores.rows if r.yoy_pct is not None), key=lambda r: r.yoy_pct or 0
        )
        if ranked_stores and (ranked_stores[0].yoy_pct or 0) < 0:
            worst = ranked_stores[0]
            insights.append(
                Insight(
                    kind="store",
                    tone="negative",
                    title=f"{worst.name} is down {abs(worst.yoy_pct or 0):.1f}% vs last year",
                    detail=f"The only store declining while the chain grew {revenue.change_pct:+.1f}%."
                    if (revenue.change_pct or 0) > 0
                    else "The steepest decline across stores.",
                )
            )
    elif revenue.change_pct is not None:
        insights.append(
            Insight(
                kind="revenue",
                tone="positive" if revenue.change_pct >= 0 else "negative",
                title=f"Revenue {'up' if revenue.change_pct >= 0 else 'down'} "
                f"{abs(revenue.change_pct):.1f}% vs last year",
                detail="Same period last year, aligned by weekday.",
            )
        )
    return insights


def _share(part: float, whole: float) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


async def trend(session: AsyncSession, weeks: int, store_id: int | None) -> TrendResponse:
    as_of = await data_as_of(session)
    # Whole weeks only: a week in progress would draw as a cliff on the chart.
    last_monday = as_of - dt.timedelta(days=as_of.weekday())
    if as_of.weekday() != 6:
        last_monday -= dt.timedelta(weeks=1)
    start = last_monday - dt.timedelta(weeks=weeks - 1)
    rows = (
        await session.execute(
            text(
                f"""
                WITH w AS (
                  SELECT date_trunc('week', sale_date)::date AS wk,
                    SUM(revenue) AS rev, SUM(units) AS units, SUM(cost) AS cost,
                    COALESCE(SUM(revenue) FILTER (WHERE promo_discount > 0), 0) AS promo
                  FROM daily_sales ds
                  WHERE {STORE_FILTER} AND sale_date >= :ly_start
                  GROUP BY 1
                )
                SELECT a.wk, a.rev, a.units, a.cost, a.promo,
                  b.rev AS rev_ly, b.units AS units_ly, b.cost AS cost_ly, b.promo AS promo_ly
                FROM w a LEFT JOIN w b ON b.wk = a.wk - 364
                WHERE a.wk >= :start AND a.wk <= :last
                ORDER BY a.wk
                """
            ),
            {"start": start, "last": last_monday, "ly_start": start - LY, "store_id": store_id},
        )
    ).all()
    events = []
    for r in rows:
        week_end = r.wk + dt.timedelta(days=6)
        for diwali in DIWALI:
            if r.wk <= diwali <= week_end:
                events.append(ChartEvent(week_start=r.wk, label=f"Diwali {diwali.year}"))
            elif r.wk - LY <= diwali <= week_end - LY:
                events.append(
                    ChartEvent(week_start=r.wk, label=f"Diwali {diwali.year} (last year)")
                )
    return TrendResponse(
        points=[
            TrendPoint(
                week_start=r.wk,
                revenue=round(float(r.rev)),
                revenue_ly=None if r.rev_ly is None else round(float(r.rev_ly)),
                units=int(r.units),
                units_ly=None if r.units_ly is None else int(r.units_ly),
                margin_pct=_share(float(r.rev) - float(r.cost), float(r.rev)),
                margin_pct_ly=None
                if r.rev_ly is None
                else _share(float(r.rev_ly) - float(r.cost_ly), float(r.rev_ly)),
                promo_pct=_share(float(r.promo), float(r.rev)),
                promo_pct_ly=None
                if r.rev_ly is None
                else _share(float(r.promo_ly), float(r.rev_ly)),
            )
            for r in rows
        ],
        events=events,
    )


async def matrix(session: AsyncSession, period: Period) -> MatrixResponse:
    """Revenue change for every store x category, the chain's map of where sales moved."""
    rows = (
        await session.execute(
            text(
                """
                SELECT s.id AS store_id, s.name || ', ' || s.city AS store, p.category,
                  COALESCE(SUM(ds.revenue) FILTER (WHERE ds.sale_date >= :start), 0) AS rev,
                  SUM(ds.revenue) FILTER (WHERE ds.sale_date <= :ly_end) AS rev_ly
                FROM daily_sales ds
                JOIN stores s ON s.id = ds.store_id
                JOIN products p ON p.id = ds.product_id
                WHERE ds.sale_date BETWEEN :start AND :end
                   OR ds.sale_date BETWEEN :ly_start AND :ly_end
                GROUP BY 1, 2, 3
                """
            ),
            period.params(),
        )
    ).all()
    by_category: dict[str, float] = {}
    for r in rows:
        by_category[r.category] = by_category.get(r.category, 0.0) + float(r.rev)
    categories = sorted(by_category, key=lambda c: -by_category[c])

    stores: dict[int, list] = {}
    for r in rows:
        stores.setdefault(r.store_id, []).append(r)
    built = []
    for store_id, cells in stores.items():
        revenue = sum(float(c.rev) for c in cells)
        known_ly = [float(c.rev_ly) for c in cells if c.rev_ly is not None]
        lookup = {c.category: c for c in cells}
        built.append(
            MatrixRow(
                store_id=store_id,
                store=cells[0].store,
                revenue=round(revenue),
                yoy_pct=pct_change(revenue, sum(known_ly)) if known_ly else None,
                cells=[
                    MatrixCell(
                        category=c,
                        revenue=round(float(lookup[c].rev)) if c in lookup else 0,
                        yoy_pct=pct_change(
                            float(lookup[c].rev),
                            None if lookup[c].rev_ly is None else float(lookup[c].rev_ly),
                        )
                        if c in lookup
                        else None,
                    )
                    for c in categories
                ],
            )
        )
    built.sort(key=lambda row: -row.revenue)
    return MatrixResponse(categories=categories, rows=built)


async def upcoming(session: AsyncSession, days: int, limit: int) -> UpcomingResponse:
    """What is about to change demand: the next festival and the promotions starting soon."""
    as_of = await data_as_of(session)
    next_diwali = min((d for d in DIWALI if d > as_of), default=None)
    rows = (
        await session.execute(
            text(
                """
                SELECT p.name AS product, p.category, pr.start_date, pr.end_date, pr.discount
                FROM promotions pr JOIN products p ON p.id = pr.product_id
                WHERE pr.start_date > :as_of AND pr.start_date <= :until
                ORDER BY pr.start_date, pr.discount DESC, p.name
                LIMIT :limit
                """
            ),
            {"as_of": as_of, "until": as_of + dt.timedelta(days=days), "limit": limit},
        )
    ).all()
    return UpcomingResponse(
        as_of=as_of,
        festival="Diwali" if next_diwali else None,
        festival_date=next_diwali,
        days_to_festival=(next_diwali - as_of).days if next_diwali else None,
        promotions=[
            UpcomingPromotion(
                product=r.product,
                category=r.category,
                start_date=r.start_date,
                end_date=r.end_date,
                discount_pct=round(float(r.discount) * 100),
            )
            for r in rows
        ],
    )


async def breakdown(
    session: AsyncSession, dimension: str, period: Period, store_id: int | None
) -> BreakdownResponse:
    if dimension == "store":
        key, name, join = "s.id", "s.name || ', ' || s.city", "JOIN stores s ON s.id = ds.store_id"
    else:
        key, name, join = "NULL::int", "p.category", ""
    rows = (
        await session.execute(
            text(
                f"""
                SELECT {key} AS id, {name} AS name,
                  COALESCE(SUM(ds.revenue) FILTER (WHERE ds.sale_date >= :start), 0) AS rev,
                  SUM(ds.revenue) FILTER (WHERE ds.sale_date <= :ly_end) AS rev_ly,
                  COALESCE(SUM(ds.cost) FILTER (WHERE ds.sale_date >= :start), 0) AS cost
                FROM daily_sales ds
                JOIN products p ON p.id = ds.product_id
                {join}
                WHERE {STORE_FILTER}
                  AND (ds.sale_date BETWEEN :start AND :end
                       OR ds.sale_date BETWEEN :ly_start AND :ly_end)
                GROUP BY 1, 2
                ORDER BY rev DESC
                """
            ),
            {**period.params(), "store_id": store_id},
        )
    ).all()
    total = sum(float(r.rev) for r in rows) or 1.0
    return BreakdownResponse(
        dimension=dimension,  # type: ignore[arg-type]
        rows=[
            BreakdownRow(
                id=r.id,
                name=r.name,
                revenue=round(float(r.rev)),
                revenue_ly=None if r.rev_ly is None else round(float(r.rev_ly)),
                yoy_pct=pct_change(float(r.rev), None if r.rev_ly is None else float(r.rev_ly)),
                margin_pct=round((float(r.rev) - float(r.cost)) / float(r.rev) * 100, 1)
                if r.rev
                else 0.0,
                share_pct=round(float(r.rev) / total * 100, 1),
            )
            for r in rows
        ],
    )


async def products(
    session: AsyncSession, sort: str, period: Period, store_id: int | None, limit: int
) -> ProductsResponse:
    order = "rev DESC" if sort == "top" else "yoy ASC NULLS LAST"
    rows = (
        await session.execute(
            text(
                f"""
                WITH agg AS (
                  SELECT p.id, p.sku, p.name, p.category,
                    COALESCE(SUM(ds.revenue) FILTER (WHERE ds.sale_date >= :start), 0) AS rev,
                    COALESCE(SUM(ds.units) FILTER (WHERE ds.sale_date >= :start), 0) AS units,
                    SUM(ds.revenue) FILTER (WHERE ds.sale_date <= :ly_end) AS rev_ly
                  FROM daily_sales ds JOIN products p ON p.id = ds.product_id
                  WHERE {STORE_FILTER}
                    AND (ds.sale_date BETWEEN :start AND :end
                         OR ds.sale_date BETWEEN :ly_start AND :ly_end)
                  GROUP BY p.id
                )
                SELECT *, (rev - rev_ly) / NULLIF(rev_ly, 0) AS yoy
                FROM agg
                -- Ignore tiny SKUs when ranking decliners: a 1-unit item halving is noise.
                WHERE :sort = 'top' OR rev_ly > 20000
                ORDER BY {order}
                LIMIT :limit
                """
            ),
            {**period.params(), "store_id": store_id, "sort": sort, "limit": limit},
        )
    ).all()
    return ProductsResponse(
        sort=sort,  # type: ignore[arg-type]
        rows=[
            ProductRow(
                product_id=r.id,
                sku=r.sku,
                name=r.name,
                category=r.category,
                revenue=round(float(r.rev)),
                units=int(r.units),
                yoy_pct=pct_change(float(r.rev), None if r.rev_ly is None else float(r.rev_ly)),
            )
            for r in rows
        ],
    )
