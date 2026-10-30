import json
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text

from app.db import engine
from app.main import app
from app.routers import analyst as analyst_router
from app.services.analyst import SUGGESTIONS
from app.services.llm import LLMError
from app.services.rate_limit import MemoryRateLimiter

pytestmark = pytest.mark.db


class FakeLLM:
    """Returns canned SQL plans in order, then streams a fixed answer."""

    def __init__(self, plans: list[dict]) -> None:
        self.plans = plans
        self.calls = 0

    async def complete_json(self, messages: list[dict]) -> tuple[dict, str]:
        plan = self.plans[min(self.calls, len(self.plans) - 1)]
        self.calls += 1
        return plan, "fake"

    async def stream(self, messages: list[dict]) -> AsyncIterator[tuple[str, str]]:
        for word in ["Revenue ", "is ", "up."]:
            yield word, "fake"


def events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


@pytest.fixture
def fake_llm():
    def install(*plans: dict) -> FakeLLM:
        llm = FakeLLM(list(plans))
        app.dependency_overrides[analyst_router.get_llm] = lambda: llm
        app.dependency_overrides[analyst_router.llm_available] = lambda: True
        return llm

    limiter = MemoryRateLimiter()
    app.dependency_overrides[analyst_router.get_rate_limiter] = lambda: limiter
    yield install
    app.dependency_overrides.clear()


async def test_health(client: httpx.AsyncClient) -> None:
    body = (await client.get("/health")).json()
    assert body["status"] == "ok" and body["database"] == "ok"


async def test_requires_auth(seeded_db) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anon:
        assert (await anon.get("/api/dashboard/summary")).status_code == 401
        bad = {"Authorization": "Bearer nope"}
        assert (await anon.get("/api/dashboard/summary", headers=bad)).status_code == 401


async def test_summary(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/dashboard/summary", params={"days": 28})).json()
    kpis = {k["key"]: k for k in body["kpis"]}
    assert kpis["revenue"]["value"] > 0 and kpis["revenue"]["change_pct"] is not None
    assert 0 < kpis["gross_margin"]["value"] < 100
    assert body["insights"], "expected at least one generated insight"


async def test_store_filter_reduces_revenue(client: httpx.AsyncClient) -> None:
    chain = (await client.get("/api/dashboard/summary")).json()["kpis"][0]["value"]
    one = (await client.get("/api/dashboard/summary", params={"store_id": 1})).json()
    assert 0 < one["kpis"][0]["value"] < chain


async def test_pune_decline_is_flagged(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/dashboard/breakdown", params={"dimension": "store"})).json()
    pune = next(r for r in body["rows"] if r["name"].startswith("Baner"))
    assert pune["yoy_pct"] < 0
    assert sum(r["share_pct"] for r in body["rows"]) == pytest.approx(100, abs=0.5)


async def test_trend_and_products(client: httpx.AsyncClient) -> None:
    trend = (await client.get("/api/dashboard/trend", params={"weeks": 12})).json()["points"]
    assert len(trend) == 12 and all(p["revenue_ly"] for p in trend)
    top = (await client.get("/api/dashboard/products", params={"sort": "top"})).json()["rows"]
    assert top == sorted(top, key=lambda r: r["revenue"], reverse=True)


async def test_trend_carries_every_metric(client: httpx.AsyncClient) -> None:
    point = (await client.get("/api/dashboard/trend", params={"weeks": 4})).json()["points"][-1]
    assert point["units"] > 0 and 0 < point["margin_pct"] < 100
    assert 0 <= point["promo_pct"] <= 100 and point["margin_pct_ly"] is not None


async def test_matrix_covers_every_store_and_category(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/dashboard/matrix", params={"days": 91})).json()
    assert len(body["rows"]) == 3 and len(body["categories"]) == 6
    assert all(len(r["cells"]) == 6 for r in body["rows"])
    pune = next(r for r in body["rows"] if r["store"].startswith("Baner"))
    assert pune["yoy_pct"] < 0
    assert sum(c["revenue"] for c in pune["cells"]) == pytest.approx(pune["revenue"], abs=6)


async def test_upcoming_names_next_diwali(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/dashboard/upcoming", params={"days": 56})).json()
    assert body["festival"] == "Diwali" and body["festival_date"] == "2026-11-08"
    assert body["days_to_festival"] == 14
    assert all(p["start_date"] > body["as_of"] for p in body["promotions"])


async def test_forecast_endpoints(client: httpx.AsyncClient) -> None:
    metrics = (await client.get("/api/forecast/metrics")).json()
    assert metrics["horizon_weeks"] == 8 and metrics["wape_model"] > 0

    alerts = (
        await client.get("/api/forecast/alerts", params={"status": "all", "limit": 400})
    ).json()
    counts = alerts["counts"]
    assert sum(counts.values()) == 3 * 12

    series = (
        await client.get("/api/forecast/series", params={"store_id": 1, "product_id": 1})
    ).json()
    future = [p for p in series["points"] if p["forecast"] is not None]
    assert len(future) == 8
    assert all(p["lower"] <= p["forecast"] <= p["upper"] for p in future)

    missing = await client.get("/api/forecast/series", params={"store_id": 99, "product_id": 1})
    assert missing.status_code == 404


async def test_every_suggestion_runs_without_an_llm(client: httpx.AsyncClient, fake_llm) -> None:
    app.dependency_overrides[analyst_router.llm_available] = lambda: False
    for suggestion in SUGGESTIONS:
        response = await client.post("/api/analyst/ask", json={"question": suggestion.question})
        stream = events(response.text)
        types = [e["type"] for e in stream]
        assert "error" not in types, (suggestion.question, stream)
        assert {"sql", "table", "chart", "answer", "done"} <= set(types)


async def test_free_form_question(client: httpx.AsyncClient, fake_llm) -> None:
    fake_llm({"sql": "SELECT city, COUNT(*) AS stores FROM stores GROUP BY city", "title": "x"})
    stream = events(
        (await client.post("/api/analyst/ask", json={"question": "stores by city?"})).text
    )
    table = next(e for e in stream if e["type"] == "table")
    assert table["columns"] == ["city", "stores"]
    answer = "".join(e["delta"] for e in stream if e["type"] == "answer")
    assert answer == "Revenue is up."
    assert stream[-1]["type"] == "done" and stream[-1]["provider"] == "fake"


async def test_second_ask_is_served_from_cache(client: httpx.AsyncClient, fake_llm) -> None:
    llm = fake_llm({"sql": "SELECT COUNT(*) AS n FROM products", "title": "Products"})
    first = events(
        (await client.post("/api/analyst/ask", json={"question": "How many SKUs?"})).text
    )
    second = events(
        (await client.post("/api/analyst/ask", json={"question": "how many skus"})).text
    )
    assert first[-1]["cached"] is False and second[-1]["cached"] is True
    assert llm.calls == 1


async def test_malicious_sql_is_blocked_then_repaired(client: httpx.AsyncClient, fake_llm) -> None:
    llm = fake_llm(
        {"sql": "DROP TABLE stores"},
        {"sql": "SELECT COUNT(*) AS store_count FROM stores", "title": "Stores"},
    )
    stream = events((await client.post("/api/analyst/ask", json={"question": "drop it"})).text)
    assert llm.calls == 2
    assert any(e["type"] == "table" for e in stream)
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT COUNT(*) FROM stores")) == 3


async def test_read_only_transaction_blocks_writes_even_if_guard_is_bypassed(seeded_db) -> None:
    from sqlalchemy.exc import DBAPIError

    from app.config import get_settings
    from app.services.analyst import execute

    with pytest.raises(DBAPIError, match="read-only"):
        await execute(engine, "DELETE FROM stores", get_settings())


async def test_unanswerable_question(client: httpx.AsyncClient, fake_llm) -> None:
    fake_llm({"unanswerable": "I can only answer questions about this retail data."})
    stream = events((await client.post("/api/analyst/ask", json={"question": "Write a poem"})).text)
    assert "only answer" in "".join(e.get("delta", "") for e in stream)
    assert not any(e["type"] == "sql" for e in stream)


async def test_question_is_not_counted_when_no_provider_answers(
    client: httpx.AsyncClient, fake_llm
) -> None:
    class DownLLM(FakeLLM):
        async def complete_json(self, messages: list[dict]) -> tuple[dict, str]:
            raise LLMError("groq: HTTPStatusError")

    fake_llm()
    app.dependency_overrides[analyst_router.get_llm] = lambda: DownLLM([])
    before = (await client.get("/api/analyst/quota")).json()["remaining_today"]
    stream = events((await client.post("/api/analyst/ask", json={"question": "anyone there"})).text)
    assert any(e["type"] == "error" for e in stream)
    assert stream[-1]["remaining"] == before
    assert (await client.get("/api/analyst/quota")).json()["remaining_today"] == before


async def test_rate_limit(client: httpx.AsyncClient, fake_llm) -> None:
    fake_llm({"sql": "SELECT 1 AS one", "title": "x"})
    codes = [
        (await client.post("/api/analyst/ask", json={"question": f"question {i}"})).status_code
        for i in range(6)
    ]
    assert codes == [200] * 5 + [429]
