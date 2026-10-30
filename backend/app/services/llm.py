"""Minimal client for OpenAI-compatible chat APIs with automatic provider fallback.

Groq and Gemini both expose OpenAI-compatible endpoints, so a single code path serves
both. If the first provider is rate-limited, down or slow, the next one is tried.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str


def configured_providers(settings: Settings) -> list[Provider]:
    providers = []
    if settings.groq_api_key:
        providers.append(
            Provider(
                "groq", "https://api.groq.com/openai/v1", settings.groq_api_key, settings.groq_model
            )
        )
    if settings.gemini_api_key:
        providers.append(
            Provider(
                "gemini",
                "https://generativelanguage.googleapis.com/v1beta/openai",
                settings.gemini_api_key,
                settings.gemini_model,
            )
        )
    return providers


class ChatModel(Protocol):
    """What the analyst needs from an LLM; tests substitute a fake."""

    async def complete_json(self, messages: list[dict]) -> tuple[dict, str]: ...

    def stream(self, messages: list[dict]) -> AsyncIterator[tuple[str, str]]: ...


def parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Some models wrap JSON in prose or code fences despite JSON mode.
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


class LLMClient:
    def __init__(self, providers: list[Provider], timeout_s: float) -> None:
        self.providers = providers
        self.timeout = httpx.Timeout(timeout_s, connect=5.0)

    def _request(self, provider: Provider, messages: list[dict], **extra) -> dict:
        return {
            "url": f"{provider.base_url}/chat/completions",
            "headers": {"Authorization": f"Bearer {provider.api_key}"},
            "json": {"model": provider.model, "messages": messages, **extra},
        }

    async def complete_json(self, messages: list[dict]) -> tuple[dict, str]:
        """Return (parsed JSON object, provider name)."""
        errors = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for provider in self.providers:
                try:
                    response = await client.post(
                        **self._request(
                            provider,
                            messages,
                            temperature=0,
                            response_format={"type": "json_object"},
                        )
                    )
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                    return parse_json(content), provider.name
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    log.warning("llm provider failed", extra={"fields": _failure(provider, exc)})
                    errors.append(f"{provider.name}: {type(exc).__name__}")
        raise LLMError("; ".join(errors) or "no LLM provider configured")

    async def stream(self, messages: list[dict]) -> AsyncIterator[tuple[str, str]]:
        """Yield (text delta, provider name). Falls back only before the first token."""
        errors = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for provider in self.providers:
                started = False
                try:
                    async with client.stream(
                        "POST", **self._request(provider, messages, temperature=0.2, stream=True)
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                break
                            choices = json.loads(data).get("choices") or [{}]
                            delta = (choices[0].get("delta") or {}).get("content")
                            if delta:
                                started = True
                                yield delta, provider.name
                    return
                except (httpx.HTTPError, ValueError) as exc:
                    if started:
                        raise LLMError(f"{provider.name} stream interrupted") from exc
                    log.warning("llm provider failed", extra={"fields": _failure(provider, exc)})
                    errors.append(f"{provider.name}: {type(exc).__name__}")
        raise LLMError("; ".join(errors) or "no LLM provider configured")


def _failure(provider: Provider, exc: Exception) -> dict:
    fields = {"provider": provider.name, "error": type(exc).__name__}
    if isinstance(exc, httpx.HTTPStatusError):
        fields["status"] = exc.response.status_code
    return fields
