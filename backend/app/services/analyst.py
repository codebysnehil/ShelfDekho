"""AI retail analyst: natural-language question -> SQL -> result -> chart -> answer.

``run`` yields a stream of events that the API forwards as server-sent events:

    status   {"message"}                       progress for the UI
    sql      {"sql"}                           the validated query that was executed
    table    {"columns", "rows", "truncated"}  query result
    chart    {"chart": {"type", "x", "y"}, "title"}
    answer   {"delta"}                         streamed answer text
    error    {"message"}                       a user-facing failure
    done     {"provider", "cached", "latency_ms"}

Suggested questions use vetted SQL so the demo path works even when every LLM
provider is down; free-form questions go through the LLM with one self-repair retry.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.db import SessionLocal
from app.models import AiCache, AiQueryLog
from app.services.calendar import DIWALI
from app.services.charts import infer_chart, plain_summary
from app.services.llm import ChatModel, LLMError
from app.services.sql_guard import UnsafeSQLError, guard_sql

log = logging.getLogger(__name__)

Event = dict


@dataclass(frozen=True)
class Suggestion:
    question: str
    sql: str
    title: str
    chart: dict = field(default_factory=dict)


SUGGESTIONS = [
    Suggestion(
        "Which stores are growing fastest vs last year?",
        """
        SELECT s.name || ', ' || s.city AS store,
          ROUND(SUM(ds.revenue) FILTER (WHERE ds.sale_date > m.max_date - 90)) AS revenue,
          ROUND(SUM(ds.revenue) FILTER (
            WHERE ds.sale_date BETWEEN m.max_date - 453 AND m.max_date - 364)) AS revenue_last_year,
          ROUND(100.0 * (SUM(ds.revenue) FILTER (WHERE ds.sale_date > m.max_date - 90)
            / NULLIF(SUM(ds.revenue) FILTER (
              WHERE ds.sale_date BETWEEN m.max_date - 453 AND m.max_date - 364), 0) - 1), 1)
            AS yoy_growth_pct
        FROM daily_sales ds
        JOIN stores s ON s.id = ds.store_id
        CROSS JOIN (SELECT MAX(sale_date) AS max_date FROM daily_sales) m
        GROUP BY s.name, s.city
        ORDER BY yoy_growth_pct DESC
        """,
        "Revenue growth vs last year, last 90 days",
        {"type": "bar", "x": "store", "y": ["yoy_growth_pct"]},
    ),
    Suggestion(
        "Why is Pune Baner's revenue falling?",
        """
        WITH monthly AS (
          SELECT date_trunc('month', ds.sale_date)::date AS month, SUM(ds.revenue) AS revenue
          FROM daily_sales ds JOIN stores s ON s.id = ds.store_id
          WHERE s.code = 'PUN01'
          GROUP BY 1
        )
        SELECT cur.month, ROUND(cur.revenue) AS revenue,
               ROUND(prev.revenue) AS revenue_last_year,
               ROUND(100.0 * (cur.revenue / prev.revenue - 1), 1) AS yoy_pct
        FROM monthly cur
        JOIN monthly prev ON prev.month = (cur.month - INTERVAL '1 year')::date
        WHERE cur.month BETWEEN DATE '2025-11-01' AND DATE '2026-09-01'
        ORDER BY cur.month
        """,
        "Pune Baner monthly revenue vs last year",
        {"type": "line", "x": "month", "y": ["revenue", "revenue_last_year"]},
    ),
    Suggestion(
        "Which SKUs will run out of stock before we can restock?",
        """
        SELECT s.name || ', ' || s.city AS store, p.name AS product, i.on_hand,
               ROUND((f.units / 7.0)::numeric, 1) AS daily_demand,
               ROUND((i.on_hand / NULLIF(f.units / 7.0, 0))::numeric, 1) AS days_of_cover,
               p.lead_time_days
        FROM inventory i
        JOIN forecasts f ON f.store_id = i.store_id AND f.product_id = i.product_id
          AND f.week_start = (SELECT MIN(week_start) FROM forecasts)
        JOIN stores s ON s.id = i.store_id
        JOIN products p ON p.id = i.product_id
        WHERE i.on_hand / NULLIF(f.units / 7.0, 0) < p.lead_time_days
        ORDER BY days_of_cover
        LIMIT 20
        """,
        "Store x SKU combinations at stock-out risk",
        {"type": "table"},
    ),
    Suggestion(
        "How much revenue came from promotions by category?",
        """
        SELECT p.category,
          ROUND(COALESCE(SUM(ds.revenue) FILTER (WHERE ds.promo_discount > 0), 0)) AS promo_revenue,
          ROUND(SUM(ds.revenue)) AS total_revenue,
          ROUND(100.0 * COALESCE(SUM(ds.revenue) FILTER (WHERE ds.promo_discount > 0), 0)
            / SUM(ds.revenue), 1) AS promo_share_pct
        FROM daily_sales ds JOIN products p ON p.id = ds.product_id
        WHERE ds.sale_date > (SELECT MAX(sale_date) FROM daily_sales) - 90
        GROUP BY p.category
        ORDER BY promo_revenue DESC
        """,
        "Promotion revenue by category, last 90 days",
        {"type": "bar", "x": "category", "y": ["promo_revenue", "total_revenue"]},
    ),
    Suggestion(
        "Which categories peaked in the run-up to Diwali 2025?",
        """
        SELECT p.category,
          ROUND(SUM(ds.revenue) FILTER (
            WHERE ds.sale_date BETWEEN DATE '2025-10-07' AND DATE '2025-10-20')) AS diwali_fortnight,
          ROUND(SUM(ds.revenue) FILTER (
            WHERE ds.sale_date BETWEEN DATE '2025-09-09' AND DATE '2025-09-22')) AS normal_fortnight,
          ROUND(100.0 * (SUM(ds.revenue) FILTER (
              WHERE ds.sale_date BETWEEN DATE '2025-10-07' AND DATE '2025-10-20')
            / NULLIF(SUM(ds.revenue) FILTER (
              WHERE ds.sale_date BETWEEN DATE '2025-09-09' AND DATE '2025-09-22'), 0) - 1), 1)
            AS uplift_pct
        FROM daily_sales ds JOIN products p ON p.id = ds.product_id
        WHERE ds.sale_date BETWEEN DATE '2025-09-09' AND DATE '2025-10-20'
        GROUP BY p.category
        ORDER BY uplift_pct DESC
        """,
        "Two weeks before Diwali 2025 vs a normal fortnight",
        {"type": "bar", "x": "category", "y": ["diwali_fortnight", "normal_fortnight"]},
    ),
    Suggestion(
        "Why did Cola 2L sales dip in Mumbai in May 2026?",
        """
        SELECT ds.sale_date, ds.units, ROUND(ds.revenue) AS revenue
        FROM daily_sales ds
        JOIN stores s ON s.id = ds.store_id
        JOIN products p ON p.id = ds.product_id
        WHERE s.code = 'MUM01' AND p.sku = 'SNB-003'
          AND ds.sale_date BETWEEN DATE '2026-04-20' AND DATE '2026-06-14'
        ORDER BY ds.sale_date
        """,
        "Cola 2L daily units, Mumbai Andheri",
        {"type": "line", "x": "sale_date", "y": ["units"]},
    ),
]


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip().lower()).rstrip("?.! ")


SUGGESTIONS_BY_KEY = {normalize_question(s.question): s for s in SUGGESTIONS}


def cache_key(question: str) -> str:
    return hashlib.sha256(normalize_question(question).encode()).hexdigest()


def sql_system_prompt(data_start: dt.date, data_end: dt.date) -> str:
    diwali = ", ".join(d.isoformat() for d in DIWALI)
    return f"""You are ShelfIQ's analytics assistant for a grocery and general-merchandise \
retail chain in India. Translate the user's question into ONE PostgreSQL SELECT query.

Schema:
stores(id, code, name, city, region, format, size_sqft)
  -- 8 stores. name is the neighbourhood (e.g. 'Baner'), city e.g. 'Pune'.
  -- region: North/West/South. format: Hypermarket/Supermarket/Express.
products(id, sku, name, category, unit_price, unit_cost, lead_time_days)
  -- 48 SKUs. category: Staples, Dairy, Snacks & Beverages, Personal Care, Home Care,
  -- Festive & Gifting.
daily_sales(sale_date, store_id, product_id, units, revenue, cost, promo_discount)
  -- one row per store, product and day. revenue/cost in INR.
  -- promo_discount = fraction off list price, 0 when not on promotion.
promotions(id, product_id, start_date, end_date, discount)
  -- chain-wide promotions, including planned future ones.
inventory(store_id, product_id, on_hand, as_of)  -- current stock snapshot
forecasts(store_id, product_id, week_start, units, lower, upper)
  -- weekly unit demand forecast for the next 8 weeks, with an 80% interval.

Facts:
- Sales data runs from {data_start} to {data_end}. Treat {data_end} as today: "last month"
  is the last full calendar month before it; "this year" is {data_end.year}; "the last N
  days" is sale_date > {data_end} - N, up to and including {data_end}.
- Weeks start on Monday: date_trunc('week', sale_date).
- Year-over-year: shift dates by 364 days so weekdays align, unless the question is about
  calendar months or years.
- Gross margin = (revenue - cost) / revenue.
- Diwali dates: {diwali}.
- Stock-out risk: on_hand / (next week's forecast units / 7) < lead_time_days. That
  ratio is days of stock, so alias it days_of_stock.

Rules:
- Only SELECT from the tables above. Never modify data.
- Alias every computed column in short snake_case. Round money to whole rupees, forecast
  units to whole units and percentages to 1 decimal (cast double precision to numeric
  before ROUND).
- At most 50 rows unless asked; order results meaningfully.
- When asked which single store or product is highest or lowest, return the top 5 so the
  answer can be compared.
- For trends over time return one row per period with the date column first.
- Match store and product names with ILIKE.

Reply with JSON only:
{{"sql": "...", "title": "short chart title",
 "chart": {{"type": "line|bar|table", "x": "column", "y": ["column"]}}}}
If the question cannot be answered from this data or is not about this business, reply:
{{"unanswerable": "one sentence on what you can help with instead"}}"""


ANSWER_PROMPT = """You are a retail analyst writing for a busy business user. Answer the \
question in 2-4 sentences using only the query result. Lead with the answer, quote specific \
numbers, and point out the most notable thing the numbers show, if there is one. Money in the \
result is already written in lakh or crore: copy those figures exactly and never convert them. \
Don't work out ratios, multiples or percentages yourself: quote the figures side by side, or \
use one only if it is in the result. Never guess at a cause. Only say why something happened when the result shows it; otherwise say \
the numbers show what changed but not why, and name what to check next. Don't mention anything \
the result has no evidence for, such as stock-outs. If the question is about Diwali, festive \
shopping peaks in the days before it, so a fall in Diwali week after a strong week before it is \
normal, not a slowdown; otherwise don't bring up festivals. If the result is empty, say so \
plainly. Plain prose only: no headings, lists or SQL, and never mention the query."""

MONEY_COLUMN = re.compile(r"(^|_)(rev|revenue|cost|sales|profit|amount|inr)(_|$)", re.IGNORECASE)
NOT_MONEY_COLUMN = re.compile(r"pct|percent|share|ratio|change|growth|units|count", re.IGNORECASE)


def format_money(value: float) -> str:
    """Models slip by a factor of 100 converting rupees to lakh, so do it for them."""
    sign, value = ("-", -value) if value < 0 else ("", value)
    if value >= 1e7:
        return f"{sign}₹{value / 1e7:.2f} crore"
    if value >= 1e5:
        return f"{sign}₹{value / 1e5:.2f} lakh"
    return f"{sign}₹{value:,.0f}"


def result_preview(columns: list[str], rows: list[list]) -> str:
    """The result as CSV for the writing step, with money already in lakh or crore."""
    money = [bool(MONEY_COLUMN.search(c)) and not NOT_MONEY_COLUMN.search(c) for c in columns]
    lines = [",".join(columns)]
    for row in rows:
        lines.append(
            ",".join(
                format_money(v) if is_money and isinstance(v, int | float) else str(v)
                for v, is_money in zip(row, money, strict=True)
            )
        )
    return "\n".join(lines)


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    return value


async def execute(
    engine: AsyncEngine, sql: str, settings: Settings
) -> tuple[list[str], list[list]]:
    """Run guarded SQL in a read-only transaction with a statement timeout."""
    async with engine.connect() as conn, conn.begin():
        await conn.execute(text("SET TRANSACTION READ ONLY"))
        await conn.execute(text(f"SET LOCAL statement_timeout = {int(settings.sql_timeout_ms)}"))
        result = await conn.exec_driver_sql(sql)
        columns = list(result.keys())
        rows = [list(r) for r in result.fetchmany(settings.sql_row_limit)]
    return columns, rows


async def data_range(engine: AsyncEngine) -> tuple[dt.date, dt.date]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT MIN(sale_date), MAX(sale_date) FROM daily_sales"))
        ).one()
    return row[0], row[1]


@dataclass
class Outcome:
    status: str = "ok"
    sql: str | None = None
    provider: str | None = None
    error: str | None = None


async def run(
    question: str,
    *,
    llm: ChatModel,
    llm_available: bool,
    engine: AsyncEngine,
    settings: Settings,
    outcome: Outcome,
) -> AsyncIterator[Event]:
    suggestion = SUGGESTIONS_BY_KEY.get(normalize_question(question))

    if suggestion:
        yield {"type": "status", "message": "Looking at the numbers"}
        sql = guard_sql(suggestion.sql, settings.sql_row_limit)
        plan = {"title": suggestion.title, "chart": suggestion.chart}
        try:
            columns, rows = await execute(engine, sql, settings)
        except DBAPIError as exc:
            outcome.status, outcome.error = "error", str(exc.orig)
            yield {"type": "error", "message": "That didn't work this time. Please try again."}
            return
    else:
        if not llm_available:
            outcome.status = "unavailable"
            yield {
                "type": "error",
                "message": "Asking your own questions is switched off in this demo. Try one of the listed questions.",
            }
            return
        yield {"type": "status", "message": "Working out what to look at"}
        result = None
        async for event in _plan_and_execute(question, llm, engine, settings, outcome):
            if event["type"] == "_result":
                result = event
            else:
                yield event
        if result is None:
            return
        sql, plan, columns, rows = result["sql"], result["plan"], result["columns"], result["rows"]

    outcome.sql = sql
    yield {"type": "sql", "sql": sql}
    chart = infer_chart(columns, rows, plan.get("chart"))
    serialised = [[_jsonable(v) for v in r] for r in rows]
    yield {
        "type": "table",
        "columns": columns,
        "rows": serialised,
        "truncated": len(rows) >= settings.sql_row_limit,
    }
    yield {"type": "chart", "chart": chart, "title": plan.get("title") or question}

    yield {"type": "status", "message": "Writing the answer"}
    if not llm_available:
        yield {
            "type": "answer",
            "delta": plain_summary(columns, rows, chart),
        }
        return

    preview = result_preview(columns, serialised[:60])
    messages = [
        {"role": "system", "content": ANSWER_PROMPT},
        {"role": "user", "content": f"Question: {question}\n\nQuery result (CSV):\n{preview}"},
    ]
    try:
        async for delta, provider in llm.stream(messages):
            outcome.provider = provider
            yield {"type": "answer", "delta": delta}
    except LLMError as exc:
        outcome.error = str(exc)
        yield {
            "type": "answer",
            "delta": plain_summary(columns, rows, chart),
        }


async def _plan_and_execute(
    question: str, llm: ChatModel, engine: AsyncEngine, settings: Settings, outcome: Outcome
) -> AsyncIterator[Event]:
    start, end = await data_range(engine)
    messages = [
        {"role": "system", "content": sql_system_prompt(start, end)},
        {"role": "user", "content": question},
    ]
    # One retry: the error is fed back so the model can repair its own SQL.
    for attempt in range(2):
        try:
            plan, provider = await llm.complete_json(messages)
        except LLMError as exc:
            outcome.status, outcome.error = "error", str(exc)
            yield {
                "type": "error",
                "message": "The analyst is busy right now. Try one of the listed questions.",
            }
            return
        outcome.provider = provider

        if plan.get("unanswerable"):
            outcome.status = "unanswerable"
            yield {"type": "answer", "delta": str(plan["unanswerable"])}
            return

        raw_sql = str(plan.get("sql") or "")
        try:
            sql = guard_sql(raw_sql, settings.sql_row_limit)
            if attempt:
                yield {"type": "status", "message": "Taking another look"}
            else:
                yield {"type": "status", "message": "Looking at the numbers"}
            columns, rows = await execute(engine, sql, settings)
        except UnsafeSQLError as exc:
            problem = f"blocked by the safety check: {exc}"
            outcome.status, outcome.sql, outcome.error = "blocked", raw_sql, str(exc)
        except DBAPIError as exc:
            problem = f"failed in Postgres: {str(exc.orig).splitlines()[0]}"
            outcome.status, outcome.sql, outcome.error = "error", raw_sql, problem
        else:
            outcome.status, outcome.error = "ok", None
            yield {"type": "_result", "sql": sql, "plan": plan, "columns": columns, "rows": rows}
            return

        messages += [
            {"role": "assistant", "content": json.dumps(plan)},
            {
                "role": "user",
                "content": f"That query {problem}. Return corrected JSON in the same format.",
            },
        ]

    yield {
        "type": "error",
        "message": "I couldn't answer that from these figures. Try rephrasing, or pick a listed question.",
    }


async def cached_events(question: str) -> list[Event] | None:
    async with SessionLocal() as session:
        row = await session.scalar(select(AiCache).where(AiCache.key == cache_key(question)))
    return None if row is None else row.payload.get("events")


async def store_cache(question: str, events: list[Event]) -> None:
    async with SessionLocal() as session:
        await session.merge(
            AiCache(key=cache_key(question), question=question, payload={"events": events})
        )
        await session.commit()


async def record(question: str, client_hash: str, outcome: Outcome, started: float, cached: bool):
    try:
        async with SessionLocal() as session:
            session.add(
                AiQueryLog(
                    client_hash=client_hash,
                    question=question[:300],
                    sql=outcome.sql,
                    status="cached" if cached else outcome.status,
                    provider=outcome.provider,
                    cached=cached,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=outcome.error,
                )
            )
            await session.commit()
    except Exception:  # logging must never break the response
        log.exception("failed to record analyst query")
