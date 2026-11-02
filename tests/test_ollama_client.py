
from __future__ import annotations

import asyncio
import json

import httpx

from shiro.ollama_client import OllamaClient


def test_ollama_client_streams_and_disables_thinking():
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        body = (
            b'{"message":{"content":"Hello"}}\n'
            b'{"message":{"content":" world"},"done":true}\n'
        )
        return httpx.Response(200, content=body)

    client = OllamaClient(
        "http://127.0.0.1:11434",
        "shiro:latest",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
    )

    async def exercise() -> list[str]:
        try:
            return [
                chunk
                async for chunk in client.stream_chat(
                    [{"role": "user", "content": "Hi"}],
                )
            ]
        finally:
            await client._client.aclose()  # type: ignore[union-attr]

    chunks = asyncio.run(exercise())

    assert chunks == ["Hello", " world"]
    assert captured["think"] is False
    assert captured["stream"] is True


def test_ollama_client_lists_installed_models():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "shiro:latest", "size": 123},
                    {"name": "qwen3.5:2b"},
                ]
            },
        )

    client = OllamaClient(
        "http://127.0.0.1:11434",
        "shiro:latest",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def exercise():
        try:
            return await client.list_models()
        finally:
            await client._client.aclose()  # type: ignore[union-attr]

    models = asyncio.run(exercise())

    assert [(model.name, model.size) for model in models] == [
        ("shiro:latest", 123),
        ("qwen3.5:2b", None),
    ]
