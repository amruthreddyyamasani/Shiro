"""Minimal asynchronous Ollama HTTP client.

The client talks only to the configured local endpoint. It deliberately does
not expose tool execution: model output is returned as text to the service.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx


class OllamaError(RuntimeError):
    """Base error for local Ollama failures."""


class OllamaConnectionError(OllamaError):
    """The local Ollama endpoint could not be reached."""


class OllamaResponseError(OllamaError):
    """Ollama returned a non-success response or malformed stream data."""


class OllamaModelInfo:
    """Small immutable description of an installed local Ollama model."""

    def __init__(self, name: str, size: int | None = None):
        self.name = name
        self.size = size


class OllamaClient:
    """Stream chat responses from Ollama's ``/api/chat`` endpoint."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 120.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = http_client
        self._owns_client = http_client is None

    async def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
    ) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "stream": True,
            # Explicitly disable thinking for supported Ollama chat models.
            "think": False,
        }
        client = await self._get_client()
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout_seconds,
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise OllamaResponseError(
                        f"Ollama returned HTTP {response.status_code}: {body[:500]}"
                    )

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise OllamaResponseError("Ollama returned invalid JSON") from exc
                    if data.get("error"):
                        raise OllamaResponseError(str(data["error"]))
                    message = data.get("message") or {}
                    content = message.get("content")
                    if content:
                        yield str(content)
                    if data.get("done") is True:
                        break
        except OllamaError:
            raise
        except (httpx.HTTPError, TimeoutError) as exc:
            raise OllamaConnectionError(
                f"Could not reach local Ollama at {self.base_url}"
            ) from exc

    async def list_models(self) -> list[OllamaModelInfo]:
        """List installed models without downloading or changing anything."""

        client = await self._get_client()
        try:
            response = await client.get(
                f"{self.base_url}/api/tags",
                timeout=self.timeout_seconds,
            )
            if response.status_code >= 400:
                raise OllamaResponseError(
                    f"Ollama returned HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )
            payload = response.json()
        except OllamaError:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError) as exc:
            raise OllamaConnectionError(
                f"Could not reach local Ollama at {self.base_url}"
            ) from exc

        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise OllamaResponseError("Ollama returned an invalid model list")

        result: list[OllamaModelInfo] = []
        for model in models:
            if not isinstance(model, dict) or not isinstance(model.get("name"), str):
                continue
            size = model.get("size")
            result.append(
                OllamaModelInfo(
                    name=model["name"],
                    size=int(size) if isinstance(size, int) else None,
                )
            )
        return result

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
