"""Pick a chart for a query result from its shape, optionally guided by the LLM's hint."""

import datetime as dt
from decimal import Decimal

TEMPORAL_HINTS = ("date", "week", "month", "day", "year", "period")


def _is_number(value: object) -> bool:
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


def infer_chart(columns: list[str], rows: list[list], hint: dict | None = None) -> dict:
    if not rows or len(columns) < 2 or (hint or {}).get("type") == "table":
        return {"type": "table"}

    def column(i: int) -> list:
        return [r[i] for r in rows if r[i] is not None]

    numeric = [c for i, c in enumerate(columns) if column(i) and all(map(_is_number, column(i)))]
    temporal = [
        c
        for i, c in enumerate(columns)
        if column(i)
        and (
            all(isinstance(v, dt.date) for v in column(i))
            or (c not in numeric and any(h in c.lower() for h in TEMPORAL_HINTS))
        )
    ]

    hint = hint or {}
    hint_x, hint_y = hint.get("x"), [y for y in (hint.get("y") or []) if y in numeric]
    if hint.get("type") in ("line", "bar") and hint_x in columns and hint_y:
        return {"type": hint["type"], "x": hint_x, "y": hint_y[:3]}

    x = temporal[0] if temporal else next((c for c in columns if c not in numeric), None)
    if x is None:
        return {"type": "table"}
    y = [c for c in numeric if c != x and not c.lower().endswith("_id")][:3]
    if not y:
        return {"type": "table"}
    if x in temporal and len(rows) >= 3:
        return {"type": "line", "x": x, "y": y}
    if len(rows) <= 30:
        return {"type": "bar", "x": x, "y": y}
    return {"type": "table"}


def _label(column: str) -> str:
    if column == "yoy_growth_pct":
        return "growth vs last year"
    return column.replace("_", " ").replace(" pct", " %")


def _figure(column: str, value: object) -> str:
    number = float(value)  # type: ignore[arg-type]
    if "pct" in column:
        return f"{number:+.1f}%"
    if any(word in column for word in ("revenue", "cost", "sales", "fortnight")):
        return f"₹{number:,.0f}"
    return f"{number:,.0f}"


def _period_word(column: str) -> str:
    name = column.lower()
    for hint, word in (("month", "months"), ("week", "weeks"), ("date", "days"), ("day", "days")):
        if hint in name:
            return word
    return "periods"


def _when(column: str, value: object) -> str:
    """A date label in words: April 2026 for a month, 11 May 2026 otherwise."""
    if isinstance(value, dt.datetime | dt.date):
        day = value
    else:
        try:
            day = dt.date.fromisoformat(str(value)[:10])
        except ValueError:
            return str(value)
    if "month" in column.lower():
        return f"{day:%B %Y}"
    return f"{day.day} {day:%b %Y}"


def plain_summary(columns: list[str], rows: list[list], chart: dict) -> str:
    """A factual answer computed from the rows, used whenever no LLM can write one."""
    if not rows:
        return "The query returned no rows."
    x, y = chart.get("x"), chart.get("y")
    if chart.get("type") == "table" or not x or not y:
        return f"{len(rows)} {'result' if len(rows) == 1 else 'results'}, listed below."

    key = y[0]
    labels = [r[columns.index(x)] for r in rows]
    values = [r[columns.index(key)] for r in rows]
    known = [(label, v) for label, v in zip(labels, values, strict=True) if v is not None]
    if not known:
        return f"No {_label(key)} figures in this result."

    if chart.get("type") == "line":
        # The longest run of zeros is usually the story: a stock-out or a closure.
        best_start, best_len, start = 0, 0, None
        for i, v in enumerate(values):
            if v == 0:
                start = i if start is None else start
                if i - start + 1 > best_len:
                    best_start, best_len = start, i - start + 1
            else:
                start = None
        if best_len >= 3:
            return (
                f"{_label(key).capitalize()} were zero for {best_len} {_period_word(x)} in a row, "
                f"from {_when(x, labels[best_start])} to "
                f"{_when(x, labels[best_start + best_len - 1])}, while the rest of the period "
                "kept selling. That pattern points to a stock-out."
            )

    pct = next((c for c in columns if "pct" in c and c != key), None)
    if pct and chart.get("type") == "line":
        # A run of periods below the comparison is the answer to "why is this falling?".
        changes = [r[columns.index(pct)] for r in rows]
        run = 0
        for change in reversed(changes):
            if change is None or float(change) >= 0:
                break
            run += 1
        if run >= 3:
            worst = min(changes[-run:], key=float)
            return (
                f"Below last year for {run} {_period_word(x)} in a row, "
                f"since {_when(x, labels[-run])}. "
                f"The latest is {_figure(pct, changes[-1])} and the worst {_figure(pct, worst)}, "
                "so this is a sustained drop rather than a one-off."
            )

    high = max(known, key=lambda item: float(item[1]))
    low = min(known, key=lambda item: float(item[1]))
    answer = (
        f"Highest {_label(key)}: {_when(x, high[0])} at {_figure(key, high[1])}. "
        f"Lowest: {_when(x, low[0])} at {_figure(key, low[1])}."
    )
    if pct and chart.get("type") == "line" and rows[-1][columns.index(pct)] is not None:
        answer += f" Latest {_label(pct)}: {_figure(pct, rows[-1][columns.index(pct)])}."
    return answer
