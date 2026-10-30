"""Fixed-window rate limiting for the public AI endpoint.

Uses Redis (e.g. Upstash's free tier) when REDIS_URL is set, so limits survive
restarts and hold across instances. Falls back to process memory otherwise.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Window:
    allowed: bool
    remaining: int
    reset_in: int


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_s: int) -> Window: ...

    async def peek(self, key: str, limit: int, window_s: int) -> Window: ...

    async def release(self, key: str, window_s: int) -> None: ...


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    @staticmethod
    def _bucket(key: str, window_s: int) -> tuple[str, int]:
        start = int(time.time()) // window_s * window_s
        return f"{key}:{window_s}:{start}", start + window_s - int(time.time())

    async def hit(self, key: str, limit: int, window_s: int) -> Window:
        bucket, reset_in = self._bucket(key, window_s)
        count = self._counts.get(bucket, 0)
        if count >= limit:
            return Window(False, 0, reset_in)
        self._counts[bucket] = count + 1
        if len(self._counts) > 10_000:  # drop expired buckets
            now = int(time.time())
            self._counts = {
                k: v for k, v in self._counts.items() if int(k.rsplit(":", 1)[1]) + 86400 > now
            }
        return Window(True, limit - count - 1, reset_in)

    async def peek(self, key: str, limit: int, window_s: int) -> Window:
        bucket, reset_in = self._bucket(key, window_s)
        count = self._counts.get(bucket, 0)
        return Window(count < limit, max(limit - count, 0), reset_in)

    async def release(self, key: str, window_s: int) -> None:
        bucket, _ = self._bucket(key, window_s)
        if self._counts.get(bucket, 0) > 0:
            self._counts[bucket] -= 1


class RedisRateLimiter:
    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self.redis = Redis.from_url(url, decode_responses=True)

    @staticmethod
    def _bucket(key: str, window_s: int) -> tuple[str, int]:
        start = int(time.time()) // window_s * window_s
        return f"rl:{key}:{window_s}:{start}", start + window_s - int(time.time())

    async def hit(self, key: str, limit: int, window_s: int) -> Window:
        bucket, reset_in = self._bucket(key, window_s)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(bucket)
            pipe.expire(bucket, window_s)
            count, _ = await pipe.execute()
        if count > limit:
            return Window(False, 0, reset_in)
        return Window(True, limit - count, reset_in)

    async def peek(self, key: str, limit: int, window_s: int) -> Window:
        bucket, reset_in = self._bucket(key, window_s)
        count = int(await self.redis.get(bucket) or 0)
        return Window(count < limit, max(limit - count, 0), reset_in)

    async def release(self, key: str, window_s: int) -> None:
        bucket, _ = self._bucket(key, window_s)
        if int(await self.redis.get(bucket) or 0) > 0:
            await self.redis.decr(bucket)
