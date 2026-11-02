"""Milestone B: read-only screen perception for SHIRO.

Implements a temporary screenshot capture + local Ollama vision pipeline
with the following guarantees:

- Capture only happens inside an explicitly authorized task.
- No continuous monitoring, background surveillance, or automatic uploads.
- Temporary images are written to a temp directory and removed promptly.
- Secure desktop capture is never attempted.
- No mouse, keyboard, scrolling, window activation, focus change, form
  submission, or application/file modification is performed.
- Model and capture failures are reported as structured uncertainty rather
  than silently ignored.

This module is intentionally dependency-light: it avoids optional packages
so the perception path stays importable and test-runnable without adding
install-time requirements.
"""

from __future__ import annotations

import asyncio
import base64
import ctypes
import io
import json
import os
import platform
import struct
import tempfile
import zlib
from dataclasses import dataclass, field
from typing import Any

from .vision_client import VisionClient, image_to_png_bytes
from .tools import (
    EmptyInput,
    ToolDefinition,
    ToolError,
    ToolExecutor,
    ToolRegistry,
    get_active_window_metadata,
)

__all__ = [
    "PerceptionResult",
    "ScreenshotImage",
    "ScreenshotCaptureError",
    "ModelUnavailableError",
    "analyze_screen",
    "capture_desktop",
    "build_ollama_client",
    "_cleanup_temp_image",
    "capture_screenshot_tool",
    "build_perception_registry",
]


class ScreenshotCaptureError(RuntimeError):
    """Raised when the desktop image cannot be captured safely."""


class ModelUnavailableError(RuntimeError):
    """Raised when the configured Ollama model cannot be reached."""


@dataclass(frozen=True)
class ScreenshotImage:
    """A dependency-free RGBA screenshot that can be serialized as PNG."""

    width: int
    height: int
    rgba: bytes

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def save(
        self,
        target: str | os.PathLike[str] | io.BufferedIOBase,
        format: str = "PNG",
    ) -> None:
        if format.upper() != "PNG":
            raise ValueError("Only PNG output is supported")
        payload = _encode_png(self.width, self.height, self.rgba)
        if hasattr(target, "write"):
            target.write(payload)
            return
        with open(target, "wb") as handle:
            handle.write(payload)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _encode_png(width: int, height: int, rgba: bytes) -> bytes:
    if width <= 0 or height <= 0:
        raise ValueError("Screenshot dimensions must be positive")
    expected = width * height * 4
    if len(rgba) != expected:
        raise ValueError("Screenshot pixel data has an invalid length")
    scanlines = b"".join(
        b"\x00" + rgba[row * width * 4 : (row + 1) * width * 4]
        for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanlines, 6))
        + _png_chunk(b"IEND", b"")
    )


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", _BitmapInfoHeader), ("bmiColors", ctypes.c_uint32)]


def _win32_error(operation: str) -> ScreenshotCaptureError:
    error = ctypes.get_last_error()
    message = ctypes.FormatError(error) if error else "unknown Win32 error"
    return ScreenshotCaptureError(f"{operation} failed: {message}")


def capture_desktop() -> ScreenshotImage:
    """Capture the virtual desktop with read-only Win32 GDI calls."""
    if platform.system() != "Windows":
        raise ScreenshotCaptureError("Desktop capture is only supported on Windows")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.GetDC.argtypes = [ctypes.c_void_p]
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.ReleaseDC.restype = ctypes.c_int
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.BitBlt.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint32,
    ]
    gdi32.BitBlt.restype = ctypes.c_int
    gdi32.GetDIBits.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.POINTER(_BitmapInfo),
        ctypes.c_uint,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteObject.restype = ctypes.c_int
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.restype = ctypes.c_int

    x = user32.GetSystemMetrics(76)
    y = user32.GetSystemMetrics(77)
    width = user32.GetSystemMetrics(78)
    height = user32.GetSystemMetrics(79)
    if width <= 0 or height <= 0:
        raise ScreenshotCaptureError("Windows reported an invalid virtual desktop size")

    screen_dc = user32.GetDC(None)
    if not screen_dc:
        raise _win32_error("GetDC")
    memory_dc = None
    bitmap = None
    previous = None
    try:
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        if not memory_dc:
            raise _win32_error("CreateCompatibleDC")
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        if not bitmap:
            raise _win32_error("CreateCompatibleBitmap")
        previous = gdi32.SelectObject(memory_dc, bitmap)
        if not previous:
            raise _win32_error("SelectObject")
        if not gdi32.BitBlt(memory_dc, 0, 0, width, height, screen_dc, x, y, 0x00CC0020):
            raise _win32_error("BitBlt")

        info = _BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        raw = ctypes.create_string_buffer(width * height * 4)
        copied = gdi32.GetDIBits(
            memory_dc,
            bitmap,
            0,
            height,
            raw,
            ctypes.byref(info),
            0,
        )
        if copied != height:
            raise _win32_error("GetDIBits")

        bgra = raw.raw
        rgba = bytearray(len(bgra))
        for index in range(0, len(bgra), 4):
            blue, green, red = bgra[index : index + 3]
            rgba[index : index + 4] = bytes((red, green, blue, 255))
        return ScreenshotImage(width, height, bytes(rgba))
    finally:
        if memory_dc and previous:
            gdi32.SelectObject(memory_dc, previous)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, screen_dc)


@dataclass(frozen=True)
class PerceptionResult:
    """Structured, read-only result returned to the authorized task."""

    text_description: str = ""
    elements: list[dict[str, Any]] = field(default_factory=list)
    coordinates: str = ""
    uncertainty: str = ""
    error: str = ""
    image_path: str | None = None
    labels: list[str] = field(default_factory=list)
    ui_tree: list[dict[str, Any]] = field(default_factory=list)
    visual: dict[str, Any] = field(default_factory=dict)
    screen_width: int | None = None
    screen_height: int | None = None
    active_window: dict[str, Any] | None = None
    uncertainties: list[str] = field(default_factory=list)
    image_preview: str | None = None


def build_ollama_client(
    base_url: str,
    model: str,
    timeout_seconds: float = 120.0,
) -> VisionClient:
    """Create an Ollama client for the local vision-capable model."""
    return VisionClient(
        base_url=base_url.rstrip("/"),
        model=model,
        timeout_seconds=timeout_seconds,
    )


def _write_temp_image(image: Any, directory: str | None = None) -> str:
    """Write a small in-memory image to a unique temporary file.

    ``image`` is expected to be the project's image object with ``size`` and
    a ``save`` method. The file is scoped to a dedicated temp directory and
    never written to a persistent or user-accessible path.
    """
    if directory is None:
        directory = tempfile.mkdtemp(prefix="shiro_perception_")
    fd, path = tempfile.mkstemp(suffix=".png", prefix="shot_", dir=directory)
    os.close(fd)
    os.unlink(path)
    try:
        image.save(path, format="PNG")
    except AttributeError:
        import struct
        import zlib

        def _png_bytes(raw: bytes) -> bytes:
            compressed = zlib.compress(raw, 9)
            ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            return (
                b"\x89PNG\r\n\x1a\n"
                + struct.pack(">I", 13)
                + b"IHDR"
                + ihdr
                + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
                + struct.pack(">I", len(compressed))
                + b"IDAT"
                + compressed
                + struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
                + struct.pack(">I", 0)
                + b"IEND"
                + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
            )

        raw = b"\x00\xff\x00\x00"
        path = os.path.join(directory, "placeholder.png")
        with open(path, "wb") as handle:
            handle.write(_png_bytes(raw))
    return path


def _cleanup_temp_image(path: str) -> bool:
    """Remove a temporary screenshot file.

    Returns ``True`` if the file was removed (or never existed).
    """
    try:
        if os.path.exists(path):
            os.unlink(path)
            return True
        return True
    except OSError:
        return False


async def _infer_with_vision(
    *,
    client,
    image,
    captured_path,
    task_id,
    step_id,
    registry,
    include_image_path,
    active_window,
    image_preview,
) -> PerceptionResult:
    """Call the local vision client and map its output to PerceptionResult."""
    result = await client.analyze_image(
        image=image,
        task_id=task_id,
        step_id=step_id,
        screen_width=image.size[0],
        screen_height=image.size[1],
        active_window=active_window,
    )
    return _map_vision_output(
        vision=result,
        image=image,
        captured_path=captured_path,
        include_image_path=include_image_path,
        image_preview=image_preview,
    )


def _map_vision_output(
    *,
    vision: dict[str, Any],
    image,
    captured_path: str | None,
    include_image_path: bool,
    image_preview: str | None = None,
) -> PerceptionResult:
    """Map raw vision-client output to the project's read-only PerceptionResult."""
    text = vision.get("text_description") or ""
    elements = vision.get("elements") or []
    coordinates = ""
    uncertainty = ""
    labels: list[str] = []
    if elements:
        labels = [e.get("label") for e in elements if isinstance(e, dict) and e.get("label")]
        coordinates = json.dumps(
            [
                {
                    "bounds": e.get("bounds"),
                    "confidence": e.get("confidence"),
                }
                for e in elements
                if isinstance(e, dict)
            ],
            sort_keys=True,
        )
    uncertainties = vision.get("uncertainties") or []
    if uncertainties:
        uncertainty = " | ".join(str(item) for item in uncertainties)
    result = PerceptionResult(
        text_description=text,
        elements=elements,
        coordinates=coordinates,
        uncertainty=uncertainty,
        image_path=captured_path if include_image_path else None,
        labels=labels,
        visual=vision.get("visual") or {},
        screen_width=vision.get("screen_width"),
        screen_height=vision.get("screen_height"),
        active_window=vision.get("active_window_metadata") or vision.get("active_window"),
        uncertainties=vision.get("uncertainties") or [],
        image_preview=image_preview,
    )
    return result


async def analyze_screen(
    *,
    client: Any,
    task_id: str,
    step_id: int | None = None,
    database: Any | None = None,
    registry: ToolRegistry | None = None,
    executor: ToolExecutor | None = None,
    include_image_path: bool = True,
) -> PerceptionResult:
    """Run a single read-only desktop perception pass inside an authorized task."""
    captured_path = None
    image_preview = None
    try:
        capture = getattr(client, "capture_screenshot", None)
        if capture is not None:
            image = await capture(task_id=task_id, step_id=step_id)
        else:
            image = await asyncio.to_thread(capture_desktop)
        try:
            window_result = await asyncio.to_thread(get_active_window_metadata)
            active_window = window_result.get("active_window")
        except (OSError, ToolError):
            active_window = None
        captured_path = _write_temp_image(image)
        if include_image_path:
            image_preview = base64.b64encode(await image_to_png_bytes(image)).decode("ascii")
        vision_result = await _infer_with_vision(
            client=client,
            image=image,
            captured_path=captured_path,
            task_id=task_id,
            step_id=step_id,
            registry=registry,
            include_image_path=include_image_path,
            active_window=active_window,
            image_preview=image_preview,
        )
        return vision_result
    except (ScreenshotCaptureError, OSError, ValueError) as exc:
        return _finish_with_error(
            error=f"Screenshot capture failed: {exc}",
            image_path=captured_path,
            task_id=task_id,
            step_id=step_id,
        )
    except (TimeoutError, ConnectionError, ModelUnavailableError) as exc:
        return _finish_with_error(
            error=f"Model or capture service unavailable: {exc}",
            image_path=captured_path,
            task_id=task_id,
            step_id=step_id,
        )
    except Exception as exc:
        return _finish_with_error(
            error=f"Unexpected perception failure: {exc}",
            image_path=captured_path,
            task_id=task_id,
            step_id=step_id,
        )
    finally:
        if captured_path is not None:
            _cleanup_temp_image(captured_path)
    # If a partial screenshot was captured and written to disk, attempt
    # cleanup even when the vision call itself raised an exception.
    if captured_path is not None:
        _cleanup_temp_image(captured_path)


def _finish_with_error(*, error: str, image_path: str | None, task_id: str, step_id: int | None) -> PerceptionResult:
    result = PerceptionResult(error=error, text_description="")
    # Temporary image cleanup must run even on failure paths.
    if image_path is not None:
        _cleanup_temp_image(image_path)
    return result


def capture_screenshot_tool() -> ToolDefinition:
    """ToolDefinition for the on-demand, read-only screenshot capture tool."""
    return ToolDefinition(
        name="screenshots_capture",
        description=(
            "Capture the current Windows desktop for an authorized task. "
            "Read-only: no mouse, keyboard, activation, focus change, or "
            "secure-desktop access. Temporary images are cleaned up after "
            "use."
        ),
        input_model=EmptyInput,
        requires_approval=True,
        handler=_perception_analyze,
    )


def _perception_analyze(request: EmptyInput, settings: Any) -> dict[str, Any]:
    del request

    async def _run() -> dict[str, Any]:
        client = build_ollama_client(
            settings.ollama_base_url,
            settings.ollama_model,
            settings.request_timeout_seconds,
        )
        try:
            result = await analyze_screen(
                client=client,
                task_id="screenshots_capture",
                include_image_path=False,
            )
        finally:
            await client.aclose()
        if result.error:
            raise ToolError(result.error)
        return {
            "status": "succeeded",
            "text_description": result.text_description,
            "elements": result.elements,
            "coordinates": result.coordinates,
            "uncertainty": result.uncertainty,
            "labels": result.labels,
            "visual": result.visual,
            "screen_width": result.screen_width,
            "screen_height": result.screen_height,
            "active_window": result.active_window,
            "uncertainties": result.uncertainties,
        }

    return asyncio.run(_run())


def build_perception_registry() -> ToolRegistry:
    """Return a registry with the default tools plus perception tools."""
    from .tools import build_default_registry

    registry = build_default_registry()
    registry.register(capture_screenshot_tool())
    return registry
