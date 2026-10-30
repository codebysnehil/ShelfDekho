import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(40))
    region: Mapped[str] = mapped_column(String(20))
    format: Mapped[str] = mapped_column(String(20))
    size_sqft: Mapped[int] = mapped_column(Integer)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40), index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    lead_time_days: Mapped[int] = mapped_column(Integer)


class DailySales(Base):
    __tablename__ = "daily_sales"
    __table_args__ = (
        Index("ix_daily_sales_store_date", "store_id", "sale_date"),
        Index("ix_daily_sales_product_date", "product_id", "sale_date"),
    )

    sale_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    units: Mapped[int] = mapped_column(Integer)
    revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # Fraction off list price, 0 when the product was not on promotion.
    promo_discount: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0)


class Promotion(Base):
    """Chain-wide price promotions, including ones planned for the coming weeks."""

    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date] = mapped_column(Date)
    discount: Mapped[Decimal] = mapped_column(Numeric(4, 2))


class Inventory(Base):
    __tablename__ = "inventory"

    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    on_hand: Mapped[int] = mapped_column(Integer)
    as_of: Mapped[dt.date] = mapped_column(Date)


class Forecast(Base):
    __tablename__ = "forecasts"

    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    week_start: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    units: Mapped[float] = mapped_column(Float)
    lower: Mapped[float] = mapped_column(Float)
    upper: Mapped[float] = mapped_column(Float)


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    series_count: Mapped[int] = mapped_column(Integer)
    horizon_weeks: Mapped[int] = mapped_column(Integer)
    backtest_weeks: Mapped[int] = mapped_column(Integer)
    wape_model: Mapped[float] = mapped_column(Float)
    wape_naive: Mapped[float] = mapped_column(Float)
    wape_seasonal_naive: Mapped[float | None] = mapped_column(Float, nullable=True)
    wape_moving_avg: Mapped[float] = mapped_column(Float)


class DataImport(Base):
    """A file of new figures that was added."""

    __tablename__ = "data_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    kind: Mapped[str] = mapped_column(String(10))
    filename: Mapped[str] = mapped_column(String(120))
    rows_added: Mapped[int] = mapped_column(Integer)
    date_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class AiCache(Base):
    __tablename__ = "ai_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AiQueryLog(Base):
    __tablename__ = "ai_query_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    client_hash: Mapped[str] = mapped_column(String(16))
    question: Mapped[str] = mapped_column(Text)
    sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cached: Mapped[bool] = mapped_column(default=False)
    latency_ms: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


# Tables the AI analyst may query. Everything else (logs, cache) is off limits.
ANALYST_TABLES = ("stores", "products", "daily_sales", "promotions", "inventory", "forecasts")
