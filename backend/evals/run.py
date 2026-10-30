"""Measure the AI analyst's text-to-SQL accuracy against reference queries.

    uv run python -m evals.run            # needs GROQ_API_KEY or GEMINI_API_KEY
    uv run python -m evals.run --limit 5

Scores execution accuracy: a case passes when the generated query runs and its
result contains every value from the reference result (rounded), so differences in
column names, ordering of columns or extra columns do not count against the model.
"""

import argparse
import asyncio
import time
from decimal import Decimal
from pathlib import Path

import yaml

from app.config import get_settings
from app.db import analyst_engine
from app.services import analyst
from app.services.llm import LLMClient, configured_providers

CASES = Path(__file__).with_name("questions.yaml")


def values(rows: list[list]) -> set[str]:
    out = set()
    for row in rows:
        for v in row:
            if isinstance(v, int | float | Decimal) and not isinstance(v, bool):
                out.add(f"{round(float(v)):d}")
            elif v is not None:
                out.add(str(v).strip().lower())
    return out


async def evaluate(limit: int | None, pause: float) -> None:
    settings = get_settings()
    providers = configured_providers(settings)
    if not providers:
        raise SystemExit("Set GROQ_API_KEY or GEMINI_API_KEY to run evals.")
    llm = LLMClient(providers, settings.llm_timeout_s)
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))[:limit]

    passed, latencies = 0, []
    for case in cases:
        _, expected = await analyst.execute(analyst_engine, case["sql"], settings)
        outcome = analyst.Outcome()
        started = time.perf_counter()
        got_rows = None
        async for event in analyst._plan_and_execute(
            case["question"], llm, analyst_engine, settings, outcome
        ):
            if event["type"] == "_result":
                got_rows = event["rows"]
        latencies.append(time.perf_counter() - started)

        ok = got_rows is not None and values(expected) <= values(got_rows)
        passed += ok
        status = "PASS" if ok else f"FAIL ({outcome.status})"
        print(f"{status:<16} {latencies[-1]:5.1f}s  {case['question']}")
        if not ok and outcome.sql:
            print(f"{'':23}{' '.join(outcome.sql.split())[:160]}")
        await asyncio.sleep(pause)

    print(
        f"\nExecution accuracy: {passed}/{len(cases)} ({passed / len(cases):.0%}), "
        f"median latency {sorted(latencies)[len(latencies) // 2]:.1f}s, "
        f"provider order: {', '.join(p.name for p in providers)}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pause", type=float, default=0, help="seconds between free-tier calls")
    args = parser.parse_args()
    asyncio.run(evaluate(args.limit, args.pause))
