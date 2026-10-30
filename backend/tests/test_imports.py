import datetime as dt
import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.services.imports import Catalog, FileProblem, parse

CATALOG = Catalog(
    stores={"del01": 1, "saket": 1},
    products={"stp-001": (7, Decimal("100"), Decimal("80"))},
    today=dt.date(2026, 10, 30),
)


def test_sales_row_works_out_revenue_and_cost() -> None:
    parsed = parse("sales", "date,store,sku,units,discount\n26-10-2026,Saket,STP-001,3,10\n", CATALOG)
    row = parsed.rows[0]
    assert row["sale_date"] == dt.date(2026, 10, 26)
    assert row["revenue"] == Decimal("270.00")
    assert row["cost"] == Decimal("240.00")
    assert row["promo_discount"] == Decimal("0.10")


def test_bad_rows_are_named_and_good_rows_kept() -> None:
    content = (
        "date,store,sku,units\n"
        "2026-10-26,DEL01,STP-001,3\n"
        "2026-10-26,NOPE,STP-001,3\n"
        "2026-10-26,DEL01,XXX,3\n"
        "2026-10-26,DEL01,STP-001,4\n"
        "2027-01-01,DEL01,STP-001,3\n"
        "2026-10-27,DEL01,STP-001,1.5\n"
        "yesterday,DEL01,STP-001,1\n"
    )
    parsed = parse("sales", content, CATALOG)
    assert len(parsed.rows) == 1
    assert parsed.rejected == 6
    problems = " ".join(i.problem for i in parsed.issues)
    assert "NOPE" in problems and "XXX" in problems and "line 2" in problems
    assert "future" in problems and "whole number" in problems and "yesterday" in problems


def test_missing_column_is_a_file_problem() -> None:
    with pytest.raises(FileProblem, match="units"):
        parse("sales", "date,store,sku\n", CATALOG)


def test_headings_from_other_systems_are_understood() -> None:
    parsed = parse("stock", "Outlet,Item Code,Closing Stock\nDEL01,stp-001,\"1,200\"\n", CATALOG)
    assert parsed.rows[0]["on_hand"] == 1200
    assert parsed.rows[0]["as_of"] == CATALOG.today


@pytest.mark.db
async def test_check_changes_nothing_and_import_updates_everything(
    client: httpx.AsyncClient,
) -> None:
    async with engine.connect() as conn:
        last = (await conn.execute(text("SELECT MAX(sale_date) FROM daily_sales"))).scalar_one()
        store = (await conn.execute(text("SELECT id, code FROM stores ORDER BY id"))).first()
        product = (await conn.execute(text("SELECT id, sku FROM products ORDER BY id"))).first()
        before = (
            await conn.execute(
                text("SELECT on_hand FROM inventory WHERE store_id=:s AND product_id=:p"),
                {"s": store.id, "p": product.id},
            )
        ).scalar_one()
        forecast_week = (
            await conn.execute(text("SELECT MIN(week_start) FROM forecasts"))
        ).scalar_one()

    # Ends midweek on purpose: that part-week must not read as a collapse in demand.
    days = [last + dt.timedelta(days=i) for i in (1, 2)]
    csv_text = "date,store,sku,units\n" + "".join(
        f"{d.isoformat()},{store.code},{product.sku},5\n" for d in days
    )
    csv_text += f"{days[0].isoformat()},NOPE,{product.sku},5\n"
    headers = {"Content-Type": "text/csv"}

    checked = await client.post(
        "/api/data/check", params={"kind": "sales"}, content=csv_text, headers=headers
    )
    assert checked.status_code == 200
    report = checked.json()
    assert (report["rows_ok"], report["rows_rejected"], report["rows_replacing"]) == (2, 1, 0)
    async with engine.connect() as conn:
        assert (
            await conn.execute(text("SELECT MAX(sale_date) FROM daily_sales"))
        ).scalar_one() == last

    name = f"{uuid.uuid4().hex[:8]}.csv"
    added = await client.post(
        "/api/data/import",
        params={"kind": "sales", "filename": name},
        content=csv_text,
        headers=headers,
    )
    assert added.status_code == 200

    status = (await client.get("/api/data/status")).json()
    # Only some stores sent these days, so the screens wait for the rest.
    assert status["sales_to"] == last.isoformat()
    summary = (await client.get("/api/dashboard/summary", params={"days": 28})).json()
    assert summary["as_of"] == last.isoformat()
    trend = (await client.get("/api/dashboard/trend", params={"weeks": 8})).json()
    assert trend["points"][-1]["week_start"] <= (last - dt.timedelta(days=6)).isoformat()
    assert status["history"][0]["filename"] == name
    async with engine.connect() as conn:
        after = (
            await conn.execute(
                text("SELECT on_hand FROM inventory WHERE store_id=:s AND product_id=:p"),
                {"s": store.id, "p": product.id},
            )
        ).scalar_one()
        new_week = (await conn.execute(text("SELECT MIN(week_start) FROM forecasts"))).scalar_one()
    assert after == max(0, before - 10)
    # The new days fall in a part-week, so that week is forecast rather than treated as finished.
    assert new_week >= forecast_week
    assert new_week == days[-1] - dt.timedelta(days=days[-1].weekday())

    # Adding the same file again replaces those days; stock does not fall twice.
    again = await client.post(
        "/api/data/import",
        params={"kind": "sales", "filename": name},
        content=csv_text,
        headers=headers,
    )
    assert again.json()["report"]["rows_replacing"] == 2
    async with engine.connect() as conn:
        assert (
            await conn.execute(
                text("SELECT on_hand FROM inventory WHERE store_id=:s AND product_id=:p"),
                {"s": store.id, "p": product.id},
            )
        ).scalar_one() == after


@pytest.mark.db
async def test_import_is_refused_when_switched_off(client: httpx.AsyncClient) -> None:
    settings = get_settings()
    settings.data_writes_enabled = False
    try:
        res = await client.post(
            "/api/data/import",
            params={"kind": "stock"},
            content="store,sku,on_hand\n",
            headers={"Content-Type": "text/csv"},
        )
    finally:
        settings.data_writes_enabled = True
    assert res.status_code == 403
    assert "demo" in res.json()["detail"]
