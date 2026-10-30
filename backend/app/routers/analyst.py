import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.auth import require_user
from app.config import Settings, get_settings
from app.db import analyst_engine
from app.schemas import AskRequest, Quota, Suggestion, SuggestionsResponse
from app.services import analyst
from app.services.llm import ChatModel, LLMClient, configured_providers
from app.services.rate_limit import MemoryRateLimiter, RateLimiter, RedisRateLimiter

router = APIRouter(prefix="/api/analyst", tags=["analyst"], dependencies=[Depends(require_user)])

DAY, MINUTE = 86400, 60


@lru_cache
def get_rate_limiter() -> RateLimiter:
    settings = get_settings()
    return RedisRateLimiter(settings.redis_url) if settings.redis_url else MemoryRateLimiter()


def get_llm(settings: Settings = Depends(get_settings)) -> ChatModel:
    return LLMClient(configured_providers(settings), settings.llm_timeout_s)


def llm_available(settings: Settings = Depends(get_settings)) -> bool:
    return bool(configured_providers(settings))


def client_id(request: Request, settings: Settings = Depends(get_settings)) -> str:
    """Stable, anonymised id per visitor. Render puts the real IP in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    return hashlib.sha256(f"{settings.jwt_secret}:{ip}".encode()).hexdigest()[:16]


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@router.get("/suggestions", response_model=SuggestionsResponse)
async def suggestions() -> SuggestionsResponse:
    return SuggestionsResponse(
        suggestions=[Suggestion(question=s.question, shows=s.title) for s in analyst.SUGGESTIONS]
    )


@router.get("/quota", response_model=Quota)
async def quota(
    client: str = Depends(client_id),
    limiter: RateLimiter = Depends(get_rate_limiter),
    settings: Settings = Depends(get_settings),
    available: bool = Depends(llm_available),
) -> Quota:
    window = await limiter.peek(f"day:{client}", settings.ai_daily_limit, DAY)
    return Quota(
        limit_per_day=settings.ai_daily_limit,
        remaining_today=window.remaining,
        limit_per_minute=settings.ai_minute_limit,
        llm_configured=available,
    )


@router.post(
    "/ask",
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "Server-sent events: status, sql, table, chart, answer, error, done.",
        },
        429: {"description": "Rate limit exceeded"},
    },
)
async def ask(
    body: AskRequest,
    client: str = Depends(client_id),
    limiter: RateLimiter = Depends(get_rate_limiter),
    llm: ChatModel = Depends(get_llm),
    available: bool = Depends(llm_available),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Answer a business question with SQL, a chart and a short written answer.

    Cached answers and suggested questions do not count against the quota.
    """
    started = time.perf_counter()
    question = body.question.strip()
    cached = await analyst.cached_events(question)

    # Suggested questions run vetted SQL and are cached after their first answer, so
    # they are free; only free-form questions (which cost LLM calls) are rate limited.
    is_suggestion = analyst.normalize_question(question) in analyst.SUGGESTIONS_BY_KEY

    remaining: int | None = None
    if cached is None and not is_suggestion:
        minute = await limiter.hit(f"min:{client}", settings.ai_minute_limit, MINUTE)
        if not minute.allowed:
            raise HTTPException(
                429,
                f"That's a lot of questions at once. Try again in {minute.reset_in} seconds.",
                headers={"Retry-After": str(minute.reset_in)},
            )
        day = await limiter.hit(f"day:{client}", settings.ai_daily_limit, DAY)
        if not day.allowed:
            raise HTTPException(
                429,
                f"You've asked your {settings.ai_daily_limit} questions for today. "
                "The listed questions still work.",
                headers={"Retry-After": str(day.reset_in)},
            )
        remaining = day.remaining

    async def stream() -> AsyncIterator[str]:
        outcome = analyst.Outcome()
        if cached is not None:
            for event in cached:
                yield sse(event)
                if event["type"] == "answer":
                    await asyncio.sleep(0.01)  # keep the typing effect on replay
            yield sse(
                {
                    "type": "done",
                    "cached": True,
                    "provider": None,
                    "remaining": None,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                }
            )
            await analyst.record(question, client, outcome, started, cached=True)
            return

        events: list[dict] = []
        async for event in analyst.run(
            question,
            llm=llm,
            llm_available=available,
            engine=analyst_engine,
            settings=settings,
            outcome=outcome,
        ):
            if event["type"] != "status":
                events.append(event)
            yield sse(event)

        # No provider answered, so the visitor got nothing for this question.
        refund = remaining is not None and outcome.status == "error" and not outcome.provider
        if refund:
            await limiter.release(f"day:{client}", DAY)

        yield sse(
            {
                "type": "done",
                "cached": False,
                "provider": outcome.provider,
                "remaining": remaining + 1 if refund else remaining,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        )
        answered = outcome.status == "ok" and outcome.provider and not outcome.error
        if answered:
            await analyst.store_cache(question, events)
        await analyst.record(question, client, outcome, started, cached=False)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
