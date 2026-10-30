"""Export a snapshot of real figures for the static landing page.

The landing page shows pieces of the product (the wall of shelves, a reorder, the sales
map, analyst answers) and must render instantly, before a sleeping free-tier API wakes.
So the figures are exported from the real dataset into a JSON file the frontend bundles:

    python -m app.jobs.snapshot ../frontend/src/lib/snapshot.json
"""

import asyncio
import json
import sys

from app.config import get_settings
from app.db import SessionLocal, engine
from app.routers.forecast import metrics
from app.services import analyst, dashboard, inventory
from app.services.charts import infer_chart, plain_summary
from app.services.sql_guard import guard_sql

SAFETY_DAYS = 14  # keep in step with the Stock screen's reorder list


async def build() -> dict:
    settings = get_settings()
    async with SessionLocal() as session:
        shelves = await inventory.alerts(session, store_id=None, status=None, limit=400)
        summary = await dashboard.summary(session, 28, None)
        trend = await dashboard.trend(session, 26, None)
        accuracy = await metrics(session)
        period = dashboard.period_ending(summary.as_of, 28)
        matrix = await dashboard.matrix(session, period)
        by_category = await dashboard.breakdown(session, "category", period, None)
        by_store = await dashboard.breakdown(session, "store", period, None)

    answers = []
    for suggestion in analyst.SUGGESTIONS:
        sql = guard_sql(suggestion.sql, settings.sql_row_limit)
        columns, rows = await analyst.execute(engine, sql, settings)
        chart = infer_chart(columns, rows, suggestion.chart)
        answers.append(
            {
                "question": suggestion.question,
                "title": suggestion.title,
                "sql": sql,
                "columns": columns,
                "rows": [[analyst._jsonable(v) for v in r] for r in rows],
                "chart": chart,
                # Computed from the rows, so the sentence can never disagree with the table.
                "answer": plain_summary(columns, rows, chart),
            }
        )

    return {
        "as_of": summary.as_of.isoformat(),
        "safety_days": SAFETY_DAYS,
        "shelves": {
            "counts": shelves.counts.model_dump(),
            "revenue_at_risk": shelves.revenue_at_risk,
            "rows": [r.model_dump() for r in shelves.rows],
        },
        "summary": summary.model_dump(mode="json"),
        "trend": trend.model_dump(mode="json"),
        "accuracy": accuracy.model_dump(mode="json"),
        "matrix": matrix.model_dump(mode="json"),
        "by_category": by_category.model_dump(mode="json"),
        "by_store": by_store.model_dump(mode="json"),
        "answers": answers,
    }


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "snapshot.json"
    data = asyncio.run(build())
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
