"""Recompute forecasts for every store x SKU and record backtest accuracy.

python -m app.jobs.forecast
"""

import asyncio
import datetime as dt
import logging
import time

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import engine as default_engine
from app.logging_config import configure_logging
from app.services import forecasting
from app.services.calendar import diwali_offsets

log = logging.getLogger(__name__)

HORIZON_WEEKS = 8
BACKTEST_WEEKS = 12

# Average discount per product per week, from the promo calendar (past and planned).
PROMO_SQL = text(
    """
    SELECT pr.product_id, w.week_start,
           SUM(pr.discount * (LEAST(pr.end_date, w.week_start + 6)
                - GREATEST(pr.start_date, w.week_start) + 1)) / 7.0 AS discount
    FROM promotions pr
    CROSS JOIN LATERAL (
        SELECT gs::date AS week_start
        FROM generate_series(date_trunc('week', pr.start_date), pr.end_date, interval '1 week') gs
    ) w
    GROUP BY 1, 2
    """
)

WEEKLY_SQL = text(
    """
    SELECT ds.store_id, ds.product_id, p.category,
           date_trunc('week', ds.sale_date)::date AS week_start,
           SUM(ds.units) AS units
    FROM daily_sales ds
    JOIN products p ON p.id = ds.product_id
    GROUP BY 1, 2, 3, 4
    """
)


async def run(engine: AsyncEngine = default_engine) -> dict:
    started = time.perf_counter()
    async with engine.connect() as conn:
        rows = (await conn.execute(WEEKLY_SQL)).all()
        max_sale_date = (await conn.execute(text("SELECT MAX(sale_date) FROM daily_sales"))).scalar()
        promo_rows = (await conn.execute(PROMO_SQL)).all()
    if not rows:
        raise RuntimeError("no sales data; run `python -m app.jobs.seed` first")

    df = pd.DataFrame(rows, columns=["store_id", "product_id", "category", "week_start", "units"])
    wide = df.pivot_table(
        index=["store_id", "product_id", "category"],
        columns="week_start",
        values="units",
        fill_value=0,
    ).sort_index(axis=1)
    # A week still in progress would read as a collapse in demand; forecast it instead.
    if max_sale_date.weekday() != 6:
        wide = wide.drop(columns=wide.columns[-1])
    weeks: list[dt.date] = list(wide.columns)
    y = wide.to_numpy(dtype=float)
    categories = wide.index.get_level_values("category")
    groups = pd.Categorical(categories).codes.astype(int)

    last_week = weeks[-1]
    future = [last_week + dt.timedelta(weeks=h + 1) for h in range(HORIZON_WEEKS)]
    all_weeks = weeks + future
    offsets = np.array(diwali_offsets(all_weeks))

    keys = wide.index.to_frame(index=False)
    promos = pd.DataFrame(promo_rows, columns=["product_id", "week_start", "discount"])
    promos["discount"] = promos["discount"].astype(float)
    by_product = (
        promos.pivot_table(index="product_id", columns="week_start", values="discount")
        .reindex(columns=all_weeks)
        .fillna(0.0)
    )
    discount = (
        by_product.reindex(keys.product_id).fillna(0.0).to_numpy(dtype=float)
        if len(promos)
        else np.zeros((len(keys), len(all_weeks)))
    )

    scores = forecasting.backtest(
        y,
        groups,
        holdout=BACKTEST_WEEKS,
        offsets=offsets[: len(weeks)],
        discount=discount[:, : len(weeks)],
    )
    result = forecasting.forecast(y, groups, HORIZON_WEEKS, offsets=offsets, discount=discount)
    forecast_rows = [
        (
            int(keys.store_id[s]),
            int(keys.product_id[s]),
            future[h],
            float(np.round(result.mean[s, h], 2)),
            float(np.round(result.lower[s, h], 2)),
            float(np.round(result.upper[s, h], 2)),
        )
        for s in range(len(keys))
        for h in range(HORIZON_WEEKS)
    ]

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM forecasts"))
        raw = await conn.get_raw_connection()
        await raw.driver_connection.copy_records_to_table(
            "forecasts",
            records=forecast_rows,
            columns=["store_id", "product_id", "week_start", "units", "lower", "upper"],
        )
        await conn.execute(
            text(
                """
                INSERT INTO forecast_runs (series_count, horizon_weeks, backtest_weeks,
                    wape_model, wape_naive, wape_seasonal_naive, wape_moving_avg)
                VALUES (:series, :horizon, :backtest, :model, :naive, :snaive, :ma)
                """
            ),
            {
                "series": len(keys),
                "horizon": HORIZON_WEEKS,
                "backtest": BACKTEST_WEEKS,
                "model": scores["model"],
                "naive": scores["naive"],
                "snaive": scores["seasonal_naive"],
                "ma": scores["moving_avg"],
            },
        )
        # Answers cached by the AI analyst may reference old forecasts.
        await conn.execute(text("DELETE FROM ai_cache"))

    log.info(
        "forecast run complete",
        extra={
            "fields": {
                "series": len(keys),
                "seconds": round(time.perf_counter() - started, 2),
                **{f"wape_{k}": v for k, v in scores.items()},
            }
        },
    )
    return scores


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
