import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class DemoUser(BaseModel):
    name: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: DemoUser


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


# --- reference data -------------------------------------------------------------


class StoreOut(BaseModel):
    id: int
    code: str
    name: str
    city: str
    region: str
    format: str


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    category: str
    unit_price: float
    lead_time_days: int


# --- dashboard ------------------------------------------------------------------


class Kpi(BaseModel):
    key: str
    label: str
    value: float
    previous: float | None
    change_pct: float | None
    unit: Literal["inr", "units", "pct"]


class Insight(BaseModel):
    kind: str
    tone: Literal["positive", "negative", "neutral"]
    title: str
    detail: str


class SummaryResponse(BaseModel):
    as_of: dt.date
    period_start: dt.date
    period_days: int
    kpis: list[Kpi]
    insights: list[Insight]


class TrendPoint(BaseModel):
    week_start: dt.date
    revenue: float
    revenue_ly: float | None
    units: int
    units_ly: int | None
    margin_pct: float
    margin_pct_ly: float | None
    promo_pct: float
    promo_pct_ly: float | None


class ChartEvent(BaseModel):
    week_start: dt.date
    label: str


class TrendResponse(BaseModel):
    points: list[TrendPoint]
    events: list[ChartEvent] = Field(description="Festival weeks to annotate on the chart")


class MatrixCell(BaseModel):
    category: str
    revenue: float
    yoy_pct: float | None


class MatrixRow(BaseModel):
    store_id: int
    store: str
    revenue: float
    yoy_pct: float | None
    cells: list[MatrixCell]


class MatrixResponse(BaseModel):
    categories: list[str]
    rows: list[MatrixRow]


class UpcomingPromotion(BaseModel):
    product: str
    category: str
    start_date: dt.date
    end_date: dt.date
    discount_pct: float


class UpcomingResponse(BaseModel):
    as_of: dt.date
    festival: str | None
    festival_date: dt.date | None
    days_to_festival: int | None
    promotions: list[UpcomingPromotion]


class BreakdownRow(BaseModel):
    id: int | None
    name: str
    revenue: float
    revenue_ly: float | None
    yoy_pct: float | None
    margin_pct: float
    share_pct: float


class BreakdownResponse(BaseModel):
    dimension: Literal["store", "category"]
    rows: list[BreakdownRow]


class ProductRow(BaseModel):
    product_id: int
    sku: str
    name: str
    category: str
    revenue: float
    units: int
    yoy_pct: float | None


class ProductsResponse(BaseModel):
    sort: Literal["top", "declining"]
    rows: list[ProductRow]


# --- forecasting ----------------------------------------------------------------

AlertStatus = Literal["stockout_risk", "overstock", "healthy"]


class ForecastMetrics(BaseModel):
    created_at: dt.datetime
    series_count: int
    horizon_weeks: int
    backtest_weeks: int
    wape_model: float
    wape_naive: float
    wape_seasonal_naive: float | None
    wape_moving_avg: float
    best_baseline: str
    improvement_pct: float = Field(description="WAPE reduction vs the best baseline, in %")


class ForecastPoint(BaseModel):
    week_start: dt.date
    actual: float | None
    forecast: float | None
    lower: float | None
    upper: float | None
    on_promo: bool


class ForecastSeries(BaseModel):
    store: StoreOut
    product: ProductOut
    on_hand: int
    days_of_cover: float | None
    status: AlertStatus
    points: list[ForecastPoint]


class AlertRow(BaseModel):
    store_id: int
    store_name: str
    product_id: int
    sku: str
    product_name: str
    category: str
    on_hand: int
    daily_demand: float
    days_of_cover: float | None
    lead_time_days: int
    status: AlertStatus
    revenue_at_risk: float
    unit_price: float


class AlertCounts(BaseModel):
    stockout_risk: int
    overstock: int
    healthy: int


class AlertsResponse(BaseModel):
    as_of: dt.date
    counts: AlertCounts
    revenue_at_risk: float
    rows: list[AlertRow]


# --- AI analyst -----------------------------------------------------------------


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300)


class Quota(BaseModel):
    limit_per_day: int
    remaining_today: int
    limit_per_minute: int
    llm_configured: bool


class Suggestion(BaseModel):
    question: str
    shows: str = Field(description="What the answer's chart shows")


class SuggestionsResponse(BaseModel):
    suggestions: list[Suggestion]


# --- Bringing in new figures -----------------------------------------------------


class ImportIssue(BaseModel):
    line: int
    problem: str


class ImportReport(BaseModel):
    kind: str
    rows_ok: int
    rows_rejected: int
    rows_replacing: int
    date_from: dt.date | None
    date_to: dt.date | None
    stores: int
    products: int
    issues: list[ImportIssue]


class ImportResult(BaseModel):
    report: ImportReport


class ImportRecord(BaseModel):
    created_at: dt.datetime
    kind: str
    filename: str
    rows_added: int
    date_from: dt.date | None
    date_to: dt.date | None


class DataStatus(BaseModel):
    sales_to: dt.date | None
    stock_to: dt.date | None
    stores: int
    products: int
    can_add: bool
    history: list[ImportRecord]
