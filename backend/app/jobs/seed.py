"""Load the synthetic dataset into Postgres.

python -m app.jobs.seed            # seed only if the database is empty
python -m app.jobs.seed --reset    # wipe and reseed
"""

import argparse
import asyncio
import datetime as dt
import logging
import time
from decimal import Decimal

import numpy as np
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import engine as default_engine
from app.logging_config import configure_logging
from app.models import Store
from app.services.synthetic import DATA_START, Dataset, generate

log = logging.getLogger(__name__)

TABLES_IN_DELETE_ORDER = [
    "ai_cache",
    "forecast_runs",
    "forecasts",
    "data_imports",
    "inventory",
    "promotions",
    "daily_sales",
    "products",
    "stores",
]


async def is_seeded(engine: AsyncEngine) -> bool:
    async with engine.connect() as conn:
        count = await conn.scalar(select(func.count()).select_from(Store))
    return bool(count)


async def reset(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(TABLES_IN_DELETE_ORDER)} RESTART IDENTITY"))


async def load(engine: AsyncEngine, data: Dataset) -> int:
    n_stores, n_products, n_days = data.units.shape
    as_of = data.dates[-1].astype(dt.date)

    stores = [
        (j + 1, s.code, s.name, s.city, s.region, s.format, s.size_sqft)
        for j, s in enumerate(data.stores)
    ]
    products = [
        (
            i + 1,
            p.sku,
            p.name,
            p.category,
            round(float(p.price), 2),
            float(data.unit_cost[i]),
            p.lead_time_days,
        )
        for i, p in enumerate(data.products)
    ]

    # Build the fact table column-wise with numpy, then hand rows to COPY.
    store_ids = np.repeat(np.arange(1, n_stores + 1), n_products * n_days)
    product_ids = np.tile(np.repeat(np.arange(1, n_products + 1), n_days), n_stores)
    day_idx = np.tile(np.arange(n_days), n_stores * n_products)
    units = data.units.reshape(-1)
    price = np.array([p.price for p in data.products])[product_ids - 1]
    discount = data.discount[product_ids - 1, day_idx]
    revenue = np.round(units * price * (1 - discount), 2)
    cost = np.round(units * data.unit_cost[product_ids - 1], 2)
    sale_dates = data.dates.astype(dt.date)[day_idx]

    def dec(x: float) -> Decimal:
        return Decimal(str(round(float(x), 2)))

    sales_rows = [
        (d, int(s), int(p), int(u), dec(r), dec(c), dec(disc))
        for d, s, p, u, r, c, disc in zip(
            sale_dates,
            store_ids,
            product_ids,
            units,
            revenue,
            cost,
            discount,
            strict=True,
        )
    ]
    promotion_rows = []
    for i in range(n_products):
        row = data.discount[i]
        day = 0
        while day < len(row):
            if row[day] > 0:
                end = day
                while end + 1 < len(row) and row[end + 1] == row[day]:
                    end += 1
                promotion_rows.append(
                    (
                        i + 1,
                        DATA_START + dt.timedelta(days=day),
                        DATA_START + dt.timedelta(days=end),
                        dec(row[day]),
                    )
                )
                day = end + 1
            else:
                day += 1

    inventory_rows = [
        (j + 1, i + 1, int(data.on_hand[j, i]), as_of)
        for j in range(n_stores)
        for i in range(n_products)
    ]

    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        pg = raw.driver_connection
        await pg.copy_records_to_table(
            "stores",
            records=stores,
            columns=["id", "code", "name", "city", "region", "format", "size_sqft"],
        )
        await pg.copy_records_to_table(
            "products",
            records=[(*p[:4], dec(p[4]), dec(p[5]), p[6]) for p in products],
            columns=[
                "id",
                "sku",
                "name",
                "category",
                "unit_price",
                "unit_cost",
                "lead_time_days",
            ],
        )
        await pg.copy_records_to_table(
            "daily_sales",
            records=sales_rows,
            columns=[
                "sale_date",
                "store_id",
                "product_id",
                "units",
                "revenue",
                "cost",
                "promo_discount",
            ],
        )
        await pg.copy_records_to_table(
            "promotions",
            records=promotion_rows,
            columns=["product_id", "start_date", "end_date", "discount"],
        )
        await pg.copy_records_to_table(
            "inventory",
            records=inventory_rows,
            columns=["store_id", "product_id", "on_hand", "as_of"],
        )
        # Explicit ids were inserted, so move the sequences past them.
        await conn.execute(text("SELECT setval('stores_id_seq', (SELECT max(id) FROM stores))"))
        await conn.execute(text("SELECT setval('products_id_seq', (SELECT max(id) FROM products))"))
    async with engine.begin() as conn:
        await conn.execute(text("ANALYZE daily_sales"))
    return len(sales_rows)


async def seed(engine: AsyncEngine = default_engine, *, force: bool = False, **gen_kwargs) -> bool:
    if force:
        await reset(engine)
    elif await is_seeded(engine):
        log.info("database already seeded, skipping")
        return False
    started = time.perf_counter()
    data = generate(**gen_kwargs)
    rows = await load(engine, data)
    log.info("seeded %d sales rows in %.1fs", rows, time.perf_counter() - started)
    return True


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe existing data first")
    args = parser.parse_args()
    asyncio.run(seed(force=args.reset))


if __name__ == "__main__":
    main()
