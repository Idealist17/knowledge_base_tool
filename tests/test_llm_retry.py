import pytest
import httpx

from learn_kg.llm_client import OpenAILLMClient


class FakeAsyncClient:
    calls = 0
    responses = []

    def __init__(self, timeout=None):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        FakeAsyncClient.calls += 1
        item = FakeAsyncClient.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.mark.asyncio
async def test_llm_retries_retryable_502(monkeypatch):
    FakeAsyncClient.calls = 0
    FakeAsyncClient.responses = [
        httpx.Response(502, text="bad gateway"),
        httpx.Response(200, json={"choices": [{"message": {"content": "{\"ok\": true}"}}]}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    async def no_sleep(*args, **kwargs):
        return None
    monkeypatch.setattr("asyncio.sleep", no_sleep)

    client = OpenAILLMClient(api_key="k", max_retries=2)
    assert await client.json("return json") == {"ok": True}
    assert FakeAsyncClient.calls == 2


@pytest.mark.asyncio
async def test_llm_does_not_retry_400(monkeypatch):
    FakeAsyncClient.calls = 0
    FakeAsyncClient.responses = [httpx.Response(400, text="bad request")]
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = OpenAILLMClient(api_key="k", max_retries=2)
    with pytest.raises(RuntimeError, match="HTTP 400"):
        await client.json("return json")
    assert FakeAsyncClient.calls == 1


@pytest.mark.asyncio
async def test_llm_retries_timeout(monkeypatch):
    FakeAsyncClient.calls = 0
    FakeAsyncClient.responses = [
        httpx.TimeoutException("timeout"),
        httpx.Response(200, json={"choices": [{"message": {"content": "[]"}}]}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    async def no_sleep(*args, **kwargs):
        return None
    monkeypatch.setattr("asyncio.sleep", no_sleep)

    client = OpenAILLMClient(api_key="k", max_retries=2)
    assert await client.json("return json") == []
    assert FakeAsyncClient.calls == 2

@pytest.mark.asyncio
async def test_agent_calls_tools_until_finish(monkeypatch):
    FakeAsyncClient.calls = 0
    FakeAsyncClient.responses = [
        httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"id": "c1", "function": {"name": "report", "arguments": "{\"x\": 1}"}}]}}]}),
        httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"id": "c2", "function": {"name": "finish", "arguments": "{}"}}]}}]}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    finished = False
    seen = []

    def report(args):
        seen.append(args)
        return "ok"

    def finish(args):
        nonlocal finished
        finished = True
        return "done"

    client = OpenAILLMClient(api_key="k", max_retries=0)
    events = await client.agent(
        system_prompt="sys",
        user_prompt="user",
        tools=[{"type": "function", "function": {"name": "report", "parameters": {"type": "object"}}}],
        tool_handlers={"report": report, "finish": finish},
        stop_condition=lambda: finished,
    )
    assert seen == [{"x": 1}]
    assert [e["tool"] for e in events] == ["report", "finish"]
    assert FakeAsyncClient.calls == 2


@pytest.mark.asyncio
async def test_agent_rejects_unknown_tool(monkeypatch):
    FakeAsyncClient.calls = 0
    FakeAsyncClient.responses = [
        httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"id": "c1", "function": {"name": "unknown", "arguments": "{}"}}]}}]}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = OpenAILLMClient(api_key="k", max_retries=0)
    with pytest.raises(RuntimeError, match="unknown tool"):
        await client.agent(system_prompt="s", user_prompt="u", tools=[], tool_handlers={}, max_turns=1)


@pytest.mark.asyncio
async def test_agent_max_turns_without_finish(monkeypatch):
    FakeAsyncClient.calls = 0
    FakeAsyncClient.responses = [
        httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"id": "c1", "function": {"name": "report", "arguments": "{}"}}]}}]}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = OpenAILLMClient(api_key="k", max_retries=0)
    with pytest.raises(RuntimeError, match="exceeded max_turns"):
        await client.agent(
            system_prompt="s",
            user_prompt="u",
            tools=[],
            tool_handlers={"report": lambda args: "ok"},
            max_turns=1,
            stop_condition=lambda: False,
        )

@pytest.mark.asyncio
async def test_agent_rejects_invalid_json_arguments(monkeypatch):
    FakeAsyncClient.calls = 0
    FakeAsyncClient.responses = [
        httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "report", "arguments": "not-json"}}]}}]}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = OpenAILLMClient(api_key="k", max_retries=0)
    with pytest.raises(RuntimeError, match="not valid JSON"):
        await client.agent(system_prompt="s", user_prompt="u", tools=[], tool_handlers={"report": lambda args: "ok"}, max_turns=1)


@pytest.mark.asyncio
async def test_agent_rejects_non_object_arguments(monkeypatch):
    FakeAsyncClient.calls = 0
    FakeAsyncClient.responses = [
        httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "report", "arguments": "[]"}}]}}]}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = OpenAILLMClient(api_key="k", max_retries=0)
    with pytest.raises(RuntimeError, match="must be a JSON object"):
        await client.agent(system_prompt="s", user_prompt="u", tools=[], tool_handlers={"report": lambda args: "ok"}, max_turns=1)


@pytest.mark.asyncio
async def test_agent_rejects_missing_tool_call_id(monkeypatch):
    FakeAsyncClient.calls = 0
    FakeAsyncClient.responses = [
        httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "tool_calls": [{"function": {"name": "report", "arguments": "{}"}}]}}]}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = OpenAILLMClient(api_key="k", max_retries=0)
    with pytest.raises(RuntimeError, match="missing an id"):
        await client.agent(system_prompt="s", user_prompt="u", tools=[], tool_handlers={"report": lambda args: "ok"}, max_turns=1)


@pytest.mark.asyncio
async def test_agent_sends_normalized_assistant_tool_message(monkeypatch):
    FakeAsyncClient.calls = 0
    captured = []

    class CapturingClient(FakeAsyncClient):
        async def post(self, *args, **kwargs):
            captured.append(kwargs["json"])
            return await super().post(*args, **kwargs)

    FakeAsyncClient.responses = [
        httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"id": "c1", "function": {"name": "report", "arguments": "{}"}}]}}]}),
        httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"id": "c2", "function": {"name": "finish", "arguments": "{}"}}]}}]}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", CapturingClient)
    finished = False

    def finish(args):
        nonlocal finished
        finished = True
        return "done"

    client = OpenAILLMClient(api_key="k", max_retries=0)
    await client.agent(
        system_prompt="s",
        user_prompt="u",
        tools=[],
        tool_handlers={"report": lambda args: "ok", "finish": finish},
        stop_condition=lambda: finished,
    )
    second_messages = captured[1]["messages"]
    assert second_messages[2]["role"] == "assistant"
    assert "content" in second_messages[2]
    assert second_messages[2]["tool_calls"][0]["id"] == "c1"
    assert second_messages[3]["role"] == "tool"
    assert second_messages[3]["tool_call_id"] == "c1"
