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
