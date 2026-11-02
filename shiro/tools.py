"""Registered, validated, approval-aware local tools for SHIRO."""

from __future__ import annotations

import ast
import asyncio
import ctypes
import ctypes.wintypes
import html
import ipaddress
import json
import math
import os
import platform
import socket
from html.parser import HTMLParser
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, Field, ValidationError
import httpx

from .config import Settings
from .database import Database


class ToolError(RuntimeError):
    """A validated tool operation could not be completed safely."""


class ToolPolicyError(ToolError):
    """The requested operation is outside the configured safety policy."""


class ListFilesInput(BaseModel):
    directory: str = Field(min_length=1, max_length=2048)
    recursive: bool = False
    max_results: int = Field(default=100, ge=1, le=500)


class SearchFilenamesInput(BaseModel):
    directory: str = Field(min_length=1, max_length=2048)
    query: str = Field(min_length=1, max_length=200)
    recursive: bool = False
    max_results: int = Field(default=100, ge=1, le=500)


class ReadTextFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=2048)
    max_chars: int = Field(default=100_000, ge=1, le=500_000)


class CreateDirectoryInput(BaseModel):
    path: str = Field(min_length=1, max_length=2048)


class CreateTextFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=2048)
    content: str = Field(max_length=500_000)
    overwrite: bool = False


class CalculateInput(BaseModel):
    expression: str = Field(min_length=1, max_length=500)


class WebSearchInput(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    max_results: int = Field(default=5, ge=1, le=10)


class WindowsListWindowsInput(BaseModel):
    only_visible: bool = Field(default=True, description="Filter for visible windows only")
    max_results: int = Field(default=50, ge=1, le=200, description="Maximum number of windows to return")


class EmptyInput(BaseModel):
    pass


@dataclass(frozen=True)
class ToolResult:
    status: str
    tool_name: str
    output: dict[str, Any] | None = None
    error: str | None = None
    approval_id: str | None = None
    audit_id: int | None = None


@dataclass(frozen=True)
class ToolContext:
    settings: Settings
    database: Database
    task_id: str | None = None
    step_id: int | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    requires_approval: bool
    handler: Callable[[BaseModel, Settings], dict[str, Any]]
    approval_checker: Callable[[BaseModel], bool] | None = None

    def needs_approval(self, validated: BaseModel) -> bool:
        return self.requires_approval or bool(
            self.approval_checker and self.approval_checker(validated)
        )


ModelT = TypeVar("ModelT", bound=BaseModel)


SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    "credentials",
    "credentials.json",
    "cookies",
    "history",
    "login data",
    "local state",
    "private.key",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx"}


def _canonical_path(raw_path: str) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(raw_path))
    return Path(expanded).resolve(strict=False)


def _sensitive(path: Path) -> bool:
    for part in path.parts:
        lowered = part.casefold()
        if lowered in {".ssh", ".gnupg", "credentials", "browser data"}:
            return True
    name = path.name.casefold()
    return name in SENSITIVE_NAMES or path.suffix.casefold() in SENSITIVE_SUFFIXES


def _approved_path(settings: Settings, raw_path: str, *, allow_missing: bool) -> Path:
    candidate = _canonical_path(raw_path)
    roots = [_canonical_path(str(root)) for root in settings.approved_roots]
    if not roots:
        raise ToolPolicyError("No approved workspace roots are configured")
    if _sensitive(candidate):
        raise ToolPolicyError("Sensitive files and credential locations are blocked")
    if not allow_missing and not candidate.exists():
        raise ToolError("Path does not exist")
    if not any(candidate == root or root in candidate.parents for root in roots):
        raise ToolPolicyError("Path is outside approved workspace roots")
    return candidate


def _relative_display(path: Path, settings: Settings) -> str:
    for root_value in settings.approved_roots:
        root = _canonical_path(str(root_value))
        if path == root or root in path.parents:
            return str(path.relative_to(root)) or "."
    return str(path)


def _list_files(request: ListFilesInput, settings: Settings) -> dict[str, Any]:
    directory = _approved_path(settings, request.directory, allow_missing=False)
    if not directory.is_dir():
        raise ToolError("Directory does not exist")
    iterator = directory.rglob("*") if request.recursive else directory.iterdir()
    files: list[str] = []
    for path in sorted(iterator, key=lambda item: str(item).casefold()):
        if len(files) >= request.max_results:
            break
        if path.is_file() and not _sensitive(path.resolve(strict=False)):
            files.append(_relative_display(path.resolve(strict=False), settings))
    return {"directory": str(directory), "files": files, "truncated": len(files) >= request.max_results}


def _search_filenames(request: SearchFilenamesInput, settings: Settings) -> dict[str, Any]:
    directory = _approved_path(settings, request.directory, allow_missing=False)
    if not directory.is_dir():
        raise ToolError("Directory does not exist")
    needle = request.query.casefold()
    iterator = directory.rglob("*") if request.recursive else directory.iterdir()
    matches: list[str] = []
    for path in sorted(iterator, key=lambda item: str(item).casefold()):
        if len(matches) >= request.max_results:
            break
        if needle in path.name.casefold() and not _sensitive(path.resolve(strict=False)):
            matches.append(_relative_display(path.resolve(strict=False), settings))
    return {"directory": str(directory), "matches": matches, "truncated": len(matches) >= request.max_results}


def _read_text_file(request: ReadTextFileInput, settings: Settings) -> dict[str, Any]:
    path = _approved_path(settings, request.path, allow_missing=False)
    if not path.is_file():
        raise ToolError("Path is not a file")
    if path.stat().st_size > settings.max_file_size_bytes:
        raise ToolPolicyError("File exceeds the configured size limit")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError("File is not valid UTF-8 text") from exc
    return {
        "path": _relative_display(path, settings),
        "content": content[: request.max_chars],
        "truncated": len(content) > request.max_chars,
    }


def _create_directory(request: CreateDirectoryInput, settings: Settings) -> dict[str, Any]:
    path = _approved_path(settings, request.path, allow_missing=True)
    if path.exists():
        raise ToolError("Directory already exists")
    parent = _approved_path(settings, str(path.parent), allow_missing=False)
    if not parent.is_dir():
        raise ToolError("Parent directory does not exist")
    path.mkdir()
    return {"path": _relative_display(path, settings), "created": True}


def _create_text_file(request: CreateTextFileInput, settings: Settings) -> dict[str, Any]:
    path = _approved_path(settings, request.path, allow_missing=True)
    if path.exists() and not request.overwrite:
        raise ToolError("File already exists; overwrite approval is required")
    if len(request.content.encode("utf-8")) > settings.max_file_size_bytes:
        raise ToolPolicyError("Content exceeds the configured size limit")
    parent = _approved_path(settings, str(path.parent), allow_missing=False)
    if not parent.is_dir():
        raise ToolError("Parent directory does not exist")
    path.write_text(request.content, encoding="utf-8", newline="")
    return {"path": _relative_display(path, settings), "created": True, "overwritten": request.overwrite}


ALLOWED_BINOPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.FloorDiv: lambda left, right: left // right,
    ast.Mod: lambda left, right: left % right,
    ast.Pow: lambda left, right: left**right,
}


def _calculate(request: CalculateInput, settings: Settings) -> dict[str, Any]:
    del settings
    try:
        tree = ast.parse(request.expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError("Invalid mathematical expression") from exc

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINOPS:
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ToolPolicyError("Exponent is too large")
            try:
                value = ALLOWED_BINOPS[type(node.op)](left, right)
            except (ArithmeticError, OverflowError) as exc:
                raise ToolError("Could not calculate expression") from exc
            if not math.isfinite(value) or abs(value) > 1e100:
                raise ToolPolicyError("Calculation result is outside safe limits")
            return value
        raise ToolError("Only basic arithmetic is supported")

    value = evaluate(tree)
    return {"expression": request.expression, "result": value}


class _SearchResultParser(HTMLParser):
    def __init__(self, max_results: int):
        super().__init__(convert_charrefs=True)
        self.max_results = max_results
        self.results: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a" or len(self.results) >= self.max_results:
            return
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        href = attributes.get("href")
        if "result__a" in classes and href:
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current_href is None:
            return
        title = html.unescape(" ".join("".join(self._current_text).split()))
        if title:
            self.results.append({"title": title, "url": self._current_href})
        self._current_href = None
        self._current_text = []


def _assert_public_host(host: str) -> None:
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ToolError("Could not resolve the approved search host") from exc
    for address in addresses:
        ip_value = address[4][0]
        parsed = ipaddress.ip_address(ip_value)
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_reserved
            or parsed.is_unspecified
        ):
            raise ToolPolicyError("Search host resolved to a prohibited network")


def _web_search(request: WebSearchInput, settings: Settings) -> dict[str, Any]:
    del settings
    host = "html.duckduckgo.com"
    _assert_public_host(host)
    endpoint = f"https://{host}/html/"
    try:
        with httpx.Client(
            timeout=15.0,
            follow_redirects=False,
            headers={"User-Agent": "SHIRO-local-agent/1.0"},
        ) as client:
            response = client.get(endpoint, params={"q": request.query})
    except httpx.HTTPError as exc:
        raise ToolError("Approved web search could not reach its destination") from exc
    if 300 <= response.status_code < 400:
        raise ToolPolicyError("Redirects are disabled for web search")
    if response.status_code != 200:
        raise ToolError(f"Web search returned HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "").casefold()
    if "text/html" not in content_type:
        raise ToolPolicyError("Web search returned an unsupported content type")
    if len(response.content) > 2_000_000:
        raise ToolPolicyError("Web search response exceeded the size limit")
    parser = _SearchResultParser(request.max_results)
    parser.feed(response.text)
    results = [
        result
        for result in parser.results
        if result["url"].startswith(("http://", "https://"))
    ]
    return {"query": request.query, "results": results}


def _windows_system_info(request: EmptyInput, settings: Settings) -> dict[str, Any]:
    del request, settings
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
    }


# Security allowlists & blacklists for Windows desktop discovery
DEFAULT_WINDOW_ALLOWLIST = {
    "notepad.exe",
    "calc.exe",
    "calculatorapp.exe",
    "mspaint.exe",
    "explorer.exe",
    "antigravity.exe",
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "code.exe",
    "systemsettings.exe",
    "applicationframehost.exe",
    "rtkuwp.exe",
    "whatsapp.root.exe",
    "chatgpt.exe",
}

PROTECTED_WINDOW_BLACKLIST = {
    "credentialuibroker.exe",
    "consent.exe",
    "taskmgr.exe",
    "regedit.exe",
    "mmc.exe",
    "keepass.exe",
    "1password.exe",
    "bitwarden.exe",
    "lastpass.exe",
    "dashlane.exe",
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "wt.exe",
}


def _get_process_name_by_pid(pid: int) -> str:
    """Retrieve process executable name safely using OpenProcess query."""
    if pid <= 0 or platform.system() != "Windows":
        return ""
    kernel32 = ctypes.windll.kernel32
    # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h_proc = kernel32.OpenProcess(0x1000, False, ctypes.wintypes.DWORD(pid))
    if not h_proc:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = ctypes.wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h_proc, 0, buffer, ctypes.byref(size)):
            full_path = buffer.value
            return full_path.split("\\")[-1].lower()
    except Exception:
        pass
    finally:
        kernel32.CloseHandle(h_proc)
    return ""


def _query_window_metadata(hwnd: int, user32: Any) -> dict[str, Any] | None:
    """Read metadata for a single window safely without changing focus or state."""
    if not user32.IsWindow(hwnd):
        return None

    length = user32.GetWindowTextLengthW(hwnd)
    title = ""
    if length > 0:
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value.strip()

    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process_pid = pid.value
    process_name = _get_process_name_by_pid(process_pid)

    # Exclude protected/sensitive applications
    if process_name in PROTECTED_WINDOW_BLACKLIST:
        return None

    # Apply allowlist: process must be in allowlist if name is known
    if process_name and process_name not in DEFAULT_WINDOW_ALLOWLIST:
        return None

    # Bounding rectangle & DPI scaling check
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    dpi = 96
    if hasattr(user32, "GetDpiForWindow"):
        try:
            dpi = user32.GetDpiForWindow(hwnd) or 96
        except Exception:
            dpi = 96

    fg_hwnd = user32.GetForegroundWindow()
    is_foreground = (hwnd == fg_hwnd)
    is_visible = bool(user32.IsWindowVisible(hwnd))

    return {
        "hwnd": hwnd,
        "title": title,
        "pid": process_pid,
        "process_name": process_name,
        "is_visible": is_visible,
        "is_foreground": is_foreground,
        "bounding_rectangle": {
            "left": rect.left,
            "top": rect.top,
            "right": rect.right,
            "bottom": rect.bottom,
            "width": max(0, rect.right - rect.left),
            "height": max(0, rect.bottom - rect.top),
        },
        "dpi": dpi,
        "dpi_scale": round(dpi / 96.0, 2),
    }


def _windows_list_windows(request: WindowsListWindowsInput, settings: Settings) -> dict[str, Any]:
    """Enumerate top-level Windows desktop windows with strict allowlist and metadata filtering."""
    del settings
    if platform.system() != "Windows":
        raise ToolError("Windows desktop discovery is only supported on Windows")

    user32 = ctypes.windll.user32
    # Ensure DPI awareness if available
    if hasattr(ctypes.windll, "shcore"):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    found_windows: list[dict[str, Any]] = []

    # Enumerate across current desktop and Default desktop station if accessible
    desktop_handles: list[int] = [0]
    try:
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            desktop_handles.append(hdesk)
    except Exception:
        pass

    seen_hwnds: set[int] = set()

    for hdesk in desktop_handles:
        desk_hwnds: list[int] = []

        def enum_cb(h: int, _: int) -> int:
            desk_hwnds.append(h)
            return 1

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        cb_func = WNDENUMPROC(enum_cb)

        if hdesk:
            user32.EnumDesktopWindows(hdesk, cb_func, 0)
        else:
            user32.EnumWindows(cb_func, 0)

        for hwnd in desk_hwnds:
            if hwnd in seen_hwnds:
                continue
            seen_hwnds.add(hwnd)

            if request.only_visible and not user32.IsWindowVisible(hwnd):
                continue

            meta = _query_window_metadata(hwnd, user32)
            if meta is not None:
                # Require non-empty title for cleaner, more relevant results
                if meta["title"]:
                    found_windows.append(meta)
                    if len(found_windows) >= request.max_results:
                        break

        if hdesk:
            user32.CloseDesktop(hdesk)

        if len(found_windows) >= request.max_results:
            break

    return {
        "count": len(found_windows),
        "windows": found_windows,
        "truncated": len(found_windows) >= request.max_results,
    }


def _windows_get_active_window(request: EmptyInput, settings: Settings) -> dict[str, Any]:
    """Retrieve metadata for the current foreground window."""
    del request, settings
    if platform.system() != "Windows":
        raise ToolError("Windows desktop discovery is only supported on Windows")

    user32 = ctypes.windll.user32
    fg_hwnd = user32.GetForegroundWindow()
    if not fg_hwnd:
        return {"active_window": None, "message": "No foreground window detected"}

    meta = _query_window_metadata(fg_hwnd, user32)
    return {"active_window": meta}


def get_active_window_metadata() -> dict[str, Any]:
    """Read the allowlisted foreground-window metadata without input actions."""
    return _windows_get_active_window(EmptyInput(), None)  # type: ignore[arg-type]


class ToolRegistry:
    """Registry of the only functions the agent is allowed to call."""

    def __init__(self, definitions: list[ToolDefinition] | None = None):
        self._definitions = {definition.name: definition for definition in definitions or []}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name)

    def list(self) -> list[ToolDefinition]:
        return sorted(self._definitions.values(), key=lambda item: item.name)


class ToolExecutor:
    """Validate, authorize, run, and audit one registered tool call."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolContext,
        approval_id: str | None = None,
    ) -> ToolResult:
        definition = self.registry.get(tool_name)
        if definition is None:
            return ToolResult("failed", tool_name, error="Unknown tool")

        try:
            validated = definition.input_model.model_validate(arguments)
            canonical_arguments = json.dumps(
                validated.model_dump(), sort_keys=True, separators=(",", ":")
            )
        except ValidationError as exc:
            return ToolResult("failed", tool_name, error=f"Invalid tool input: {exc}")

        if definition.needs_approval(validated):
            if approval_id is None:
                approval = context.database.create_tool_approval(
                    tool_name=tool_name,
                    arguments_json=canonical_arguments,
                    affected_resources_json=json.dumps(_affected_resources(validated)),
                    reason=f"The tool {tool_name} requires explicit approval before execution.",
                    task_id=context.task_id,
                    step_id=context.step_id,
                    expires_at=datetime.now(UTC) + timedelta(minutes=15),
                )
                return ToolResult("approval_required", tool_name, approval_id=approval.id)

            approval = context.database.get_tool_approval(approval_id)
            if (
                approval is None
                or approval.tool_name != tool_name
                or approval.arguments_json != canonical_arguments
                or approval.task_id != context.task_id
                or approval.step_id != context.step_id
            ):
                return ToolResult("denied", tool_name, error="Approval does not match this operation")
            if approval.status != "approved":
                return ToolResult("denied", tool_name, error="Tool approval was not granted")
            if not context.database.consume_tool_approval(approval_id):
                return ToolResult("denied", tool_name, error="Approval is expired or already consumed")

        started_at = datetime.now(UTC)
        try:
            output = await asyncio.wait_for(
                asyncio.to_thread(definition.handler, validated, context.settings),
                timeout=context.settings.max_task_execution_seconds,
            )
            finished_at = datetime.now(UTC)
            audit = context.database.record_tool_audit(
                tool_name,
                canonical_arguments,
                "succeeded",
                json.dumps(output, ensure_ascii=False),
                None,
                started_at,
                finished_at,
                task_id=context.task_id,
                step_id=context.step_id,
            )
            return ToolResult("succeeded", tool_name, output=output, audit_id=audit.id)
        except asyncio.TimeoutError:
            error = "Tool execution timed out"
        except (ToolError, OSError) as exc:
            error = str(exc)
        except Exception as exc:  # defensive boundary around registered tools
            error = f"Tool failed: {exc}"

        finished_at = datetime.now(UTC)
        audit = context.database.record_tool_audit(
            tool_name,
            canonical_arguments,
            "failed",
            None,
            error,
            started_at,
            finished_at,
            task_id=context.task_id,
            step_id=context.step_id,
        )
        return ToolResult("failed", tool_name, error=error, audit_id=audit.id)


def _affected_resources(arguments: BaseModel) -> list[str]:
    values = arguments.model_dump()
    resources = [str(values[key]) for key in ("path", "directory") if values.get(key)]
    if values.get("query"):
        resources.append("https://html.duckduckgo.com/html/")
    return resources


def build_default_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ToolDefinition("list_files", "List files in an approved directory.", ListFilesInput, False, _list_files),
            ToolDefinition("search_filenames", "Search filenames in an approved directory.", SearchFilenamesInput, False, _search_filenames),
            ToolDefinition("read_text_file", "Read an approved UTF-8 text file.", ReadTextFileInput, False, _read_text_file),
            ToolDefinition("create_directory", "Create a new directory in an approved workspace.", CreateDirectoryInput, True, _create_directory),
            ToolDefinition("create_text_file", "Create a new UTF-8 text file in an approved workspace.", CreateTextFileInput, True, _create_text_file),
            ToolDefinition("calculate", "Safely calculate a basic mathematical expression.", CalculateInput, False, _calculate),
            ToolDefinition("web_search", "Search the public web through one approved search endpoint.", WebSearchInput, True, _web_search),
            ToolDefinition("windows_system_info", "Read non-sensitive Windows and runtime metadata.", EmptyInput, False, _windows_system_info),
            ToolDefinition("windows_list_windows", "List accessible top-level desktop windows within the application allowlist.", WindowsListWindowsInput, False, _windows_list_windows),
            ToolDefinition("windows_get_active_window", "Get metadata for the current foreground window.", EmptyInput, False, _windows_get_active_window),
        ]
    )
