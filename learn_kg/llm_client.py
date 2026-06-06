from __future__ import annotations
import json
import random
import asyncio
import time
from collections.abc import Callable
from typing import Any

import httpx


class LLMClient:
    async def json(self, prompt: str, *, schema_name: str = "response") -> Any:
        raise NotImplementedError


class OpenAILLMClient(LLMClient):
    def __init__(
        self,
        model: str = "gpt-5.4-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        logger: Callable[[str], None] | None = None,
        timeout: float = 120,
        max_retries: int = 5,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.logger = logger
        self.timeout = timeout
        self.max_retries = max_retries

    async def json(self, prompt: str, *, schema_name: str = "response") -> Any:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

        # Use a minimal OpenAI-compatible HTTP request instead of the OpenAI SDK.
        # Some relays/WAFs reject SDK-specific x-stainless headers and return a
        # vague 403 `Your request was blocked`, while the same payload succeeds
        # with a plain HTTP client.
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = await self._post_with_retries(schema_name, prompt, headers, payload)

        body = resp.json()
        text = body.get("choices", [{}])[0].get("message", {}).get("content") or "{}"
        data = json.loads(text)
        if self.logger:
            size = len(data) if isinstance(data, list | dict) else "n/a"
            self.logger(f"[dim]LLM parsed[/dim] schema={schema_name} type={type(data).__name__} size={size}")
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        return data

    async def _post_with_retries(self, schema_name: str, prompt: str, headers: dict[str, str], payload: dict[str, Any]) -> httpx.Response:
        last_error: str | None = None
        for attempt in range(1, self.max_retries + 2):
            started = time.monotonic()
            if self.logger:
                retry_suffix = f" attempt={attempt}/{self.max_retries + 1}" if attempt > 1 else ""
                self.logger(f"[dim]LLM request[/dim] schema={schema_name} model={self.model} prompt_chars={len(prompt):,}{retry_suffix}")
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                elapsed = time.monotonic() - started
                last_error = f"{type(exc).__name__}: {exc}"
                if self.logger:
                    self.logger(f"[yellow]LLM transport error[/yellow] schema={schema_name} elapsed={elapsed:.1f}s error={last_error}")
                if attempt <= self.max_retries:
                    await self._sleep_before_retry(attempt, schema_name)
                    continue
                raise RuntimeError(f"LLM request failed after {attempt} attempts: {last_error}") from exc

            elapsed = time.monotonic() - started
            if self.logger:
                self.logger(f"[dim]LLM response[/dim] schema={schema_name} status={resp.status_code} elapsed={elapsed:.1f}s")
            if resp.status_code < 400:
                return resp
            body_preview = resp.text[:1000]
            last_error = f"HTTP {resp.status_code}: {body_preview}"
            if self._is_retryable_status(resp.status_code) and attempt <= self.max_retries:
                if self.logger:
                    self.logger(f"[yellow]LLM retryable error[/yellow] schema={schema_name} status={resp.status_code} retrying")
                await self._sleep_before_retry(attempt, schema_name)
                continue
            raise RuntimeError(f"LLM request failed after {attempt} attempts: {last_error}")
        raise RuntimeError(f"LLM request failed: {last_error or 'unknown error'}")

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code < 600

    async def _sleep_before_retry(self, attempt: int, schema_name: str) -> None:
        delay = min(30.0, 1.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
        if self.logger:
            self.logger(f"[yellow]LLM retry sleep[/yellow] schema={schema_name} delay={delay:.1f}s")
        await asyncio.sleep(delay)


class MockLLMClient(LLMClient):
    def __init__(self, responses: list[Any] | None = None):
        self.responses = list(responses or [])
        self.prompts: list[str] = []

    async def json(self, prompt: str, *, schema_name: str = "response") -> Any:
        self.prompts.append(prompt)
        if self.responses:
            return self.responses.pop(0)
        return []
