import datetime as dt
from decimal import Decimal

import pytest

from app.db import normalize_database_url
from app.services.analyst import result_preview
from app.services.charts import infer_chart, plain_summary
from app.services.inventory import classify
from app.services.llm import parse_json
from app.services.rate_limit import MemoryRateLimiter


def test_line_chart_for_time_series() -> None:
    rows = [[dt.date(2026, 1, i), Decimal(i * 10)] for i in range(1, 6)]
    assert infer_chart(["day", "revenue"], rows) == {"type": "line", "x": "day", "y": ["revenue"]}


def test_bar_chart_for_categories() -> None:
    rows = [["Dairy", 10.0, 3], ["Staples", 20.0, 4]]
    chart = infer_chart(["category", "revenue", "units"], rows)
    assert chart == {"type": "bar", "x": "category", "y": ["revenue", "units"]}


def test_table_when_nothing_to_plot() -> None:
    assert infer_chart(["name", "city"], [["Baner", "Pune"]]) == {"type": "table"}
    assert infer_chart(["revenue"], [[1.0]]) == {"type": "table"}


def test_valid_llm_hint_wins_and_invalid_hint_is_ignored() -> None:
    rows = [["Dairy", 10.0, 3], ["Staples", 20.0, 4]]
    hint = {"type": "bar", "x": "category", "y": ["units"]}
    assert infer_chart(["category", "revenue", "units"], rows, hint)["y"] == ["units"]
    bad = {"type": "line", "x": "nope", "y": ["category"]}
    assert infer_chart(["category", "revenue", "units"], rows, bad)["type"] == "bar"


@pytest.mark.parametrize(
    ("on_hand", "demand", "lead", "status"),
    [(5, 2.0, 7, "stockout_risk"), (30, 2.0, 7, "healthy"), (500, 2.0, 7, "overstock")],
)
def test_stock_classification(on_hand: int, demand: float, lead: int, status: str) -> None:
    assert classify(on_hand, demand, lead)[1] == status


def test_dead_stock_is_overstock() -> None:
    assert classify(10, 0.0, 7) == (None, "overstock")


async def test_memory_rate_limiter() -> None:
    limiter = MemoryRateLimiter()
    results = [await limiter.hit("ip", 3, 60) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[2].remaining == 0
    assert (await limiter.peek("other-ip", 3, 60)).remaining == 3


def test_parse_json_tolerates_fences() -> None:
    assert parse_json('```json\n{"sql": "SELECT 1"}\n```') == {"sql": "SELECT 1"}


def test_normalizes_neon_url() -> None:
    url, args = normalize_database_url(
        "postgres://u:p@ep-x-pooler.neon.tech/db?sslmode=require&channel_binding=require"
    )
    assert url == "postgresql+asyncpg://u:p@ep-x-pooler.neon.tech/db"
    assert args == {"ssl": "require", "statement_cache_size": 0}


def test_table_hint_is_respected() -> None:
    assert infer_chart(["a", "b"], [["x", 1]], {"type": "table"}) == {"type": "table"}


def test_plain_summary_names_a_run_of_zeros() -> None:
    rows = [[dt.date(2026, 5, d), u] for d, u in enumerate([9, 0, 0, 0, 7], start=10)]
    text = plain_summary(
        ["sale_date", "units"], rows, {"type": "line", "x": "sale_date", "y": ["units"]}
    )
    assert "zero for 3 days" in text and "11 May 2026" in text and "stock-out" in text


def test_plain_summary_names_a_sustained_drop() -> None:
    rows = [[f"2026-0{m}-01", 100, v] for m, v in enumerate([2, -3, -9, -5], start=1)]
    text = plain_summary(
        ["month", "revenue", "yoy_pct"], rows, {"type": "line", "x": "month", "y": ["revenue"]}
    )
    assert "3 months in a row, since February 2026" in text and "-5.0%" in text and "-9.0%" in text


def test_plain_summary_ranks_bars_and_handles_empty() -> None:
    rows = [["Dairy", Decimal("10")], ["Staples", Decimal("30")]]
    text = plain_summary(
        ["category", "revenue"], rows, {"type": "bar", "x": "category", "y": ["revenue"]}
    )
    assert "Staples at ₹30" in text and "Dairy at ₹10" in text
    assert plain_summary(["a"], [], {"type": "table"}) == "The query returned no rows."


def test_money_reaches_the_writer_in_lakh_and_crore() -> None:
    preview = result_preview(
        ["month", "total_revenue", "cost", "revenue_pct", "prev_units"],
        [["2026-09", 4877512.0, 12500000, 12.5, 46910], ["2026-08", 900.0, None, 1.0, 5]],
    )
    assert preview.splitlines() == [
        "month,total_revenue,cost,revenue_pct,prev_units",
        "2026-09,₹48.78 lakh,₹1.25 crore,12.5,46910",
        "2026-08,₹900,None,1.0,5",
    ]
