"""Composable tool registry for the read-only Milestone B perception tools.

This module exposes a single helper so that the FastAPI app can register the
read-only perception tools (screenshot capture + local Ollama vision) without
modifying the existing ``build_default_registry`` implementation.
"""

from __future__ import annotations

from shiro.input_control import DesktopInputController, desktop_input_tool
from shiro.perception import capture_screenshot_tool
from shiro.tools import ToolRegistry, build_default_registry


def build_perception_registry(
    input_controller: DesktopInputController | None = None,
) -> ToolRegistry:
    """Return the default registry plus perception and bounded input tools."""
    registry = build_default_registry()
    registry.register(capture_screenshot_tool())
    registry.register(desktop_input_tool(input_controller))
    return registry
