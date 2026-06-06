from __future__ import annotations
import inspect
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

    async def agent(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        tool_handlers: dict[str, Callable[[dict[str, Any]], Any]],
        schema_name: str = "agent",
        max_turns: int = 16,
        stop_condition: Callable[[], bool] | None = None,
    ) -> Any:
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
        headers = self._headers()
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

    async def agent(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        tool_handlers: dict[str, Callable[[dict[str, Any]], Any]],
        schema_name: str = "agent",
        max_turns: int = 16,
        stop_condition: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        if max_turns <= 0:
            raise ValueError("max_turns must be positive")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        tool_events: list[dict[str, Any]] = []
        headers = self._headers()

        for turn in range(1, max_turns + 1):
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
            }
            resp = await self._post_with_retries(schema_name, user_prompt, headers, payload)
            body = resp.json()
            message = body.get("choices", [{}])[0].get("message", {}) or {}
            tool_calls = message.get("tool_calls") or []
            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": message.get("content"),
            }
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)
            if not tool_calls:
                if stop_condition and stop_condition():
                    return tool_events
                raise RuntimeError(f"Agent {schema_name} returned no tool calls before finish on turn {turn}")

            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name")
                if not name or name not in tool_handlers:
                    raise RuntimeError(f"Agent {schema_name} called unknown tool: {name!r}")
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"Agent {schema_name} tool {name} arguments are not valid JSON: {raw_args}") from exc
                if not isinstance(args, dict):
                    raise RuntimeError(f"Agent {schema_name} tool {name} arguments must be a JSON object")
                tool_call_id = call.get("id")
                if not tool_call_id:
                    raise RuntimeError(f"Agent {schema_name} tool call for {name} is missing an id")
                result = tool_handlers[name](args)
                if inspect.isawaitable(result):
                    result = await result
                result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                tool_events.append({"tool": name, "args": args, "result": result_text})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_text,
                })

            if stop_condition and stop_condition():
                if self.logger:
                    self.logger(f"[dim]Agent finished[/dim] schema={schema_name} turns={turn} tool_calls={len(tool_events)}")
                return tool_events

        raise RuntimeError(f"Agent {schema_name} exceeded max_turns={max_turns} without finish")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

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

    async def agent(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        tool_handlers: dict[str, Callable[[dict[str, Any]], Any]],
        schema_name: str = "agent",
        max_turns: int = 16,
        stop_condition: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        self.prompts.append(user_prompt)
        if not self.responses:
            return []
        script = self.responses.pop(0)
        if isinstance(script, dict):
            script = [script]
        if not isinstance(script, list):
            raise RuntimeError(f"Mock agent response for {schema_name} must be a tool-call script list")

        events: list[dict[str, Any]] = []
        for idx, event in enumerate(script, start=1):
            if idx > max_turns:
                raise RuntimeError(f"Agent {schema_name} exceeded max_turns={max_turns} without finish")
            if not isinstance(event, dict) or "tool" not in event:
                raise RuntimeError(f"Mock agent event must be {{'tool': name, 'args': {{...}}}}, got {event!r}")
            name = event["tool"]
            if name not in tool_handlers:
                raise RuntimeError(f"Agent {schema_name} called unknown tool: {name!r}")
            args = event.get("args") or {}
            if not isinstance(args, dict):
                raise RuntimeError(f"Mock agent args for {name} must be a dict")
            result = tool_handlers[name](args)
            if inspect.isawaitable(result):
                result = await result
            result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            events.append({"tool": name, "args": args, "result": result_text})
        if stop_condition and stop_condition():
            return events
        raise RuntimeError(f"Agent {schema_name} exceeded scripted tool calls without finish")
