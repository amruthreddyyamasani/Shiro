"""Validated visual-understanding models used by computer-control planning."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NormalizedBounds(BaseModel):
    """A bounding box normalized to the captured screenshot dimensions."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def stay_inside_frame(self) -> "NormalizedBounds":
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("Normalized bounds must stay inside the screenshot")
        return self


class VisualTarget(BaseModel):
    """One visible target that may be considered by a future action planner."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    role: str = Field(default="other", min_length=1, max_length=40)
    bounds: NormalizedBounds | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    visible_text: str = Field(default="", max_length=500)
    interactable: bool = False
    uncertainties: list[str] = Field(default_factory=list, max_length=10)


class ActiveWindowInfo(BaseModel):
    """Allowlisted metadata for the foreground window at capture time."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=500)
    process_name: str = Field(default="", max_length=200)
    hwnd: int | None = Field(default=None, ge=1)
    pid: int | None = Field(default=None, ge=1)
    is_visible: bool = True
    is_foreground: bool = True
    bounding_rectangle: dict[str, int] | None = None


class VisualUnderstanding(BaseModel):
    """The only visual result that may be passed to action planning."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["shiro.visual.v1"]
    screen_width: int = Field(ge=1, le=16_000)
    screen_height: int = Field(ge=1, le=16_000)
    active_window: ActiveWindowInfo | None = None
    targets: list[VisualTarget] = Field(default_factory=list, max_length=100)
    visible_text: list[str] = Field(default_factory=list, max_length=200)
    uncertainties: list[str] = Field(default_factory=list, max_length=20)


def parse_visual_response(
    raw: str,
    *,
    screen_width: int,
    screen_height: int,
    active_window: dict[str, Any] | None = None,
) -> VisualUnderstanding:
    """Parse and validate model JSON; prose is never accepted as action input."""
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Ollama returned non-JSON visual output") from exc
    if not isinstance(payload, dict):
        raise ValueError("Ollama visual output must be a JSON object")

    if active_window is not None:
        payload["active_window"] = {
            key: active_window[key]
            for key in (
                "title",
                "process_name",
                "hwnd",
                "pid",
                "is_visible",
                "is_foreground",
                "bounding_rectangle",
            )
            if key in active_window
        }
    # Some local multimodal models return pixel-space boxes even when the
    # prompt requests normalized coordinates. Convert only when the payload
    # dimensions match the capture and each box is safely inside that frame.
    # The action layer still receives one canonical normalized format.
    if payload.get("screen_width") == screen_width and payload.get("screen_height") == screen_height:
        for target in payload.get("targets") or []:
            bounds = target.get("bounds") if isinstance(target, dict) else None
            if not isinstance(bounds, dict):
                continue
            values = [bounds.get(key) for key in ("x", "y", "width", "height")]
            if any(isinstance(value, (int, float)) and value > 1 for value in values):
                if not all(isinstance(value, (int, float)) for value in values):
                    continue
                x, y, width, height = values
                if (
                    x >= 0
                    and y >= 0
                    and width > 0
                    and height > 0
                    and x + width <= screen_width
                    and y + height <= screen_height
                ):
                    target["bounds"] = {
                        "x": x / screen_width,
                        "y": y / screen_height,
                        "width": width / screen_width,
                        "height": height / screen_height,
                    }
    visual = VisualUnderstanding.model_validate(payload)
    if (visual.screen_width, visual.screen_height) != (screen_width, screen_height):
        raise ValueError(
            "Visual response dimensions do not match the captured screenshot"
        )
    return visual


def visual_description(visual: VisualUnderstanding) -> str:
    """Produce a concise human-readable summary from validated visual data."""
    parts: list[str] = []
    if visual.active_window and visual.active_window.title:
        parts.append(f"Active window: {visual.active_window.title}")
    if visual.targets:
        labels = ", ".join(target.label for target in visual.targets[:12])
        parts.append(f"Visible targets: {labels}")
    if visual.visible_text:
        parts.append(f"Visible text: {' | '.join(visual.visible_text[:12])}")
    return ". ".join(parts) or "No reliable visual targets were identified."
