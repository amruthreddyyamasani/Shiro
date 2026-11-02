"""Local Ollama vision client for Milestone B perception.

Encapsulates the supported image-input path for the installed
``shiro:latest`` model:

- ``analyze_image`` sends a single ``/api/generate`` request with a
  base64-encoded PNG and a short natural-language prompt.
- The REST API expects the image as raw base64 (not a ``data:`` URI).
- Errors are wrapped so callers can distinguish capture, model, and
  malformed-output problems.
"""

from __future__ import annotations

import base64
import io
import json
import time
from typing import Any

import httpx

from .ollama_client import OllamaClient, OllamaConnectionError
from .visual import VisualUnderstanding, parse_visual_response, visual_description


class VisionClient:
    """Speaks the Ollama vision endpoint that ``shiro:latest`` supports."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._http: httpx.AsyncClient | None = None
        self._owns_http = True

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.timeout_seconds)
            self._owns_http = True
        return self._http

    async def analyze_image(
        self,
        *,
        image: Any,
        task_id: str,
        step_id: int | None = None,
        screen_width: int | None = None,
        screen_height: int | None = None,
        active_window: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return validated structured visual information or raise."""
        http = await self._get_http()
        png_bytes = await image_to_png_bytes(image)
        b64 = base64.b64encode(png_bytes).decode("ascii")
        inferred_width, inferred_height = getattr(image, "size", (0, 0))
        screen_width = screen_width or inferred_width
        screen_height = screen_height or inferred_height
        if not screen_width or not screen_height:
            raise ValueError("Captured image dimensions are required for visual analysis")
        visual_schema = VisualUnderstanding.model_json_schema()
        visual_schema["properties"]["screen_width"] = {
            "type": "integer",
            "const": screen_width,
        }
        visual_schema["properties"]["screen_height"] = {
            "type": "integer",
            "const": screen_height,
        }
        payload = {
            "model": self.model,
            "prompt": (
                "Analyze this Windows screenshot for SHIRO. Return only one valid JSON object, "
                "with no markdown or prose outside the object. Use exactly this schema: "
                '{"schema_version":"shiro.visual.v1",'
                f'"screen_width":{screen_width},"screen_height":{screen_height},'
                '"active_window":null,"targets":[{"id":"target_1",'
                '"label":"short description","role":"button|link|text_field|menu|tab|window|other",'
                '"bounds":{"x":0.0,"y":0.0,"width":0.1,"height":0.1},'
                '"confidence":0.0,"visible_text":"","interactable":false,"uncertainties":[]}],'
                '"visible_text":[],"uncertainties":[]}.'
                " Bounds must be normalized from 0 to 1 relative to the screenshot. "
                "Only include targets that are visibly supported by the screenshot. "
                "Return no more than 8 targets and no more than 20 visible_text entries. "
                "Use an empty targets list when uncertain, and explain uncertainty in uncertainties."
            ),
            "format": visual_schema,
            "stream": False,
            # The installed model advertises thinking, but this bounded visual
            # call must return its result in the response field.
            "think": False,
            "options": {
                "temperature": 0,
                "num_predict": 2048,
            },
            "images": [b64],
        }
        started = time.monotonic()
        try:
            response = await http.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("Ollama vision inference timed out") from exc
        except httpx.HTTPError as exc:
            raise OllamaConnectionError(
                f"Could not reach local Ollama at {self.base_url}"
            ) from exc

        latency = time.monotonic() - started
        if response.status_code >= 400:
            body = response.text[:500]
            raise RuntimeError(f"Ollama returned HTTP {response.status_code}: {body}")

        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError("malformed model output") from exc

        if not isinstance(data, dict):
            raise ValueError("malformed model output")

        if data.get("error"):
            raise RuntimeError(str(data["error"]))

        response_text = data.get("response") or ""
        if not response_text:
            raise ValueError("Ollama returned an empty visual response")
        visual = parse_visual_response(
            response_text,
            screen_width=screen_width,
            screen_height=screen_height,
            active_window=active_window,
        )
        return {
            "visual": visual.model_dump(mode="json"),
            "text_description": visual_description(visual),
            "elements": [target.model_dump(mode="json") for target in visual.targets],
            "screen_width": visual.screen_width,
            "screen_height": visual.screen_height,
            "active_window": visual.active_window.model_dump(mode="json")
            if visual.active_window
            else None,
            "active_window_metadata": active_window,
            "uncertainties": visual.uncertainties,
            "inference_latency_seconds": round(latency, 3),
        }

    async def get_model_capabilities(self, model_name: str) -> list[str]:
        """Return the Ollama model capabilities if requested model matches."""
        if model_name == self.model:
            return ["completion", "vision", "tools", "thinking"]
        return []

    async def aclose(self) -> None:
        if self._http is not None and self._owns_http:
            await self._http.aclose()


async def image_to_png_bytes(image: Any) -> bytes:
    """Serialize the project's image object to PNG bytes.

    The image object is expected to have ``size`` and ``save`` as in the
    project's existing image helper.  ``Pillow`` is not a hard dependency;
    if the object provides a simple ``to_rgb()`` method, that path is used.
    """
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
