"""Bounded visual-first observe, act, verify execution for SHIRO.

The runner never reuses coordinates from an earlier observation. Each pointer
action names a target from the current observation, is resolved to its current
center, passes through ``ToolExecutor``, and is followed by a fresh screenshot
and verification pass.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import Settings
from .input_control import ActionName, DesktopInputController, DesktopInputRequest
from .ollama_client import OllamaClient
from .perception import PerceptionResult, analyze_screen, build_ollama_client
from .tools import ToolContext, ToolExecutor, ToolResult
from .visual import VisualUnderstanding


class VisualTaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=4_000)
    max_actions: int = Field(default=15, ge=1, le=15)
    max_duration_seconds: float = Field(default=300.0, gt=0, le=900)
    max_consecutive_failures: int = Field(default=3, ge=1, le=5)


class ProposedVisualAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ActionName
    target_id: str | None = Field(default=None, max_length=100)
    amount: int | None = Field(default=None, ge=-20, le=20)
    text: str | None = Field(default=None, max_length=4_000)
    key: str | None = Field(default=None, max_length=32)
    keys: list[str] | None = Field(default=None, min_length=2, max_length=4)

    @model_validator(mode="after")
    def validate_proposal(self) -> "ProposedVisualAction":
        if self.action in {"move", "click", "double_click", "right_click", "scroll"} and not self.target_id:
            raise ValueError("pointer actions must identify a target from the current observation")
        if self.action == "scroll" and not self.amount:
            raise ValueError("scroll actions need a non-zero amount")
        if self.action == "type_text" and not self.text:
            raise ValueError("type_text actions need text")
        if self.action == "press_key" and not self.key:
            raise ValueError("press_key actions need a key")
        if self.action == "hotkey" and not self.keys:
            raise ValueError("hotkey actions need keys")
        return self


class VisualVerificationExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visible_text_contains: list[str] = Field(default_factory=list, max_length=10)
    active_window_title_contains: str | None = Field(default=None, max_length=200)
    active_window_process_name: str | None = Field(default=None, max_length=200)


class VisualPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(min_length=1, max_length=100)
    done: bool = False
    reason: str = Field(default="", max_length=500)
    action: ProposedVisualAction | None = None
    verification: VisualVerificationExpectation = Field(default_factory=VisualVerificationExpectation)


@dataclass
class _RunControl:
    pause_event: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        self.pause_event.set()


class VisualExecutionManager:
    """Own a runtime state mirror backed by persisted visual-task records."""

    def __init__(
        self,
        settings: Settings,
        database: Any,
        executor: ToolExecutor,
        input_controller: DesktopInputController,
        ollama: OllamaClient,
    ) -> None:
        self.settings = settings
        self.database = database
        self.executor = executor
        self.input_controller = input_controller
        self.ollama = ollama
        self._states: dict[str, dict[str, Any]] = {}
        self._controls: dict[str, _RunControl] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        persisted_tasks = self.database.list_visual_tasks() if self.database is not None else []
        for persisted in persisted_tasks:
            run_id = str(persisted["run_id"])
            state = dict(persisted)
            state["latest_screenshot"] = None
            state["recent_actions"] = [
                {
                    "action": item["action"],
                    "status": item["status"],
                    "verification": item["verification"],
                    "error": item["error"],
                }
                for item in self.database.list_visual_actions(run_id, limit=10)
            ]
            state["next_action_sequence"] = len(
                self.database.list_visual_actions(run_id, limit=10000)
            ) + 1
            self._states[run_id] = state
            control = _RunControl()
            if state.get("recovery_required"):
                control.pause_event.clear()
            self._controls[run_id] = control

    def _persist_state(self, run_id: str) -> None:
        if self.database is None:
            return
        state = self._states[run_id]
        self.database.update_visual_task(
            run_id,
            status=state["status"],
            action_count=state["action_count"],
            consecutive_failures=state["consecutive_failures"],
            current_action_json=json.dumps(state["current_action"], ensure_ascii=False)
            if state.get("current_action") is not None
            else None,
            latest_observation_json=json.dumps(state["latest_observation"], ensure_ascii=False)
            if state.get("latest_observation") is not None
            else None,
            latest_verification_json=json.dumps(state["latest_verification"], ensure_ascii=False)
            if state.get("latest_verification") is not None
            else None,
            approval_id=state.get("approval_id"),
            error=state.get("error"),
            recovery_required=1 if state.get("recovery_required") else 0,
        )

    def _set_status(self, run_id: str, status: str, error: str | None = None) -> None:
        state = self._states[run_id]
        state["status"] = status
        if error is not None:
            state["error"] = error
        self._persist_state(run_id)

    def _record_action(
        self,
        run_id: str,
        action: dict[str, Any],
        status: str,
        *,
        verification: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        state = self._states[run_id]
        sequence = int(state.get("next_action_sequence", 1))
        if self.database is not None:
            self.database.record_visual_action(
                run_id,
                sequence,
                action,
                status,
                verification=verification,
                error=error,
            )
        state["next_action_sequence"] = sequence + 1
        state["recent_actions"].append(
            {
                "action": action,
                "status": status,
                "verification": verification,
                "error": error,
            }
        )
        state["recent_actions"] = state["recent_actions"][-10:]
        self._persist_state(run_id)

    def create(self, request: VisualTaskRequest) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        self._states[run_id] = {
            "run_id": run_id,
            "task": request.task,
            "status": "queued",
            "action_count": 0,
            "max_actions": request.max_actions,
            "max_duration_seconds": request.max_duration_seconds,
            "consecutive_failures": 0,
            "max_consecutive_failures": request.max_consecutive_failures,
            "current_action": None,
            "latest_observation": None,
            "latest_screenshot": None,
            "latest_verification": None,
            "recent_actions": [],
            "approval_id": None,
            "error": None,
            "recovery_required": False,
            "next_action_sequence": 1,
        }
        self._controls[run_id] = _RunControl()
        if self.database is not None:
            self.database.create_visual_task(
                run_id,
                request.task,
                max_actions=request.max_actions,
                max_duration_seconds=request.max_duration_seconds,
                max_consecutive_failures=request.max_consecutive_failures,
            )
        return dict(self._states[run_id])

    def start(self, run_id: str) -> dict[str, Any]:
        if run_id not in self._states:
            raise KeyError(run_id)
        if self._states[run_id].get("recovery_required"):
            return self.get(run_id)
        task = self._tasks.get(run_id)
        if task is None or task.done():
            self._tasks[run_id] = asyncio.create_task(self._run(run_id))
        return self.get(run_id)

    def get(self, run_id: str) -> dict[str, Any]:
        if run_id not in self._states:
            raise KeyError(run_id)
        return dict(self._states[run_id])

    def pause(self, run_id: str) -> dict[str, Any]:
        control = self._controls[run_id]
        if self._states[run_id].get("recovery_required"):
            return self.get(run_id)
        control.pause_event.clear()
        if self._states[run_id]["status"] not in {"succeeded", "failed", "cancelled", "stopped"}:
            self._states[run_id]["status"] = "paused"
            self._persist_state(run_id)
        return self.get(run_id)

    def resume(self, run_id: str) -> dict[str, Any]:
        control = self._controls[run_id]
        if self._states[run_id].get("recovery_required"):
            return self.get(run_id)
        control.pause_event.set()
        if self._states[run_id]["status"] == "paused":
            self._states[run_id]["status"] = "running"
            self._persist_state(run_id)
        return self.get(run_id)

    def cancel(self, run_id: str) -> dict[str, Any]:
        control = self._controls[run_id]
        control.cancel_event.set()
        control.pause_event.set()
        if self._states[run_id]["status"] not in {"succeeded", "failed"}:
            self._states[run_id]["status"] = "cancelled"
        self._persist_state(run_id)
        return self.get(run_id)

    def emergency_stop(self, reason: str = "emergency_stop") -> None:
        self.input_controller.stop()
        for run_id, control in self._controls.items():
            control.cancel_event.set()
            control.pause_event.set()
            if self._states[run_id]["status"] not in {"succeeded", "failed", "cancelled"}:
                self._states[run_id]["status"] = "stopped"
                self._states[run_id]["error"] = f"Emergency stop: {reason}"
                self._persist_state(run_id)
        now = datetime.now(UTC)
        if self.database is not None:
            self.database.record_tool_audit(
                "emergency_stop",
                json.dumps({"reason": reason}, sort_keys=True),
                "triggered",
                json.dumps({"status": "stopped"}),
                None,
                now,
                datetime.now(UTC),
            )

    async def _wait_for_control(self, run_id: str) -> tuple[bool, bool]:
        control = self._controls[run_id]
        if control.cancel_event.is_set():
            self._set_status(run_id, "cancelled")
            return False, False
        was_paused = not control.pause_event.is_set()
        if was_paused:
            self._set_status(run_id, "paused")
            await control.pause_event.wait()
        if control.cancel_event.is_set():
            self._set_status(run_id, "cancelled")
            return False, was_paused
        return True, was_paused

    async def _observe(self, run_id: str, vision_client: Any) -> tuple[str, VisualUnderstanding] | None:
        self._set_status(run_id, "observing")
        result: PerceptionResult = await analyze_screen(
            client=vision_client,
            task_id=run_id,
            include_image_path=True,
        )
        if result.error or not result.visual:
            self._states[run_id]["error"] = result.error or "No structured visual result was returned"
            return None
        try:
            visual = VisualUnderstanding.model_validate(result.visual)
        except ValueError as exc:
            self._states[run_id]["error"] = f"Invalid visual observation: {exc}"
            return None
        observation_id = str(uuid.uuid4())
        self._states[run_id]["latest_observation"] = {
            "id": observation_id,
            "visual": visual.model_dump(mode="json"),
            "text_description": result.text_description,
            "uncertainties": result.uncertainties,
        }
        self._states[run_id]["latest_screenshot"] = (
            f"data:image/png;base64,{result.image_preview}" if result.image_preview else None
        )
        self._persist_state(run_id)
        return observation_id, visual

    async def _plan(
        self,
        task: str,
        observation_id: str,
        visual: VisualUnderstanding,
    ) -> VisualPlanResponse:
        system = (
            "You are SHIRO's local visual action planner. Return only valid JSON. "
            "Never invent a target id; use only target ids in the observation. "
            "For pointer actions, target_id is required and coordinates are not accepted. "
            "If the task is complete, set done=true and action=null. If confidence is low, "
            "set action=null and explain the need for clarification. Keep one action only. "
            "Schema: {observation_id, done, reason, action:{action,target_id,amount,text,key,keys}, "
            "verification:{visible_text_contains,active_window_title_contains,active_window_process_name}}"
        )
        prompt = json.dumps(
            {
                "task": task,
                "observation_id": observation_id,
                "observation": visual.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
        parts: list[str] = []
        async for token in self.ollama.stream_chat([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]):
            parts.append(token)
            if sum(len(part) for part in parts) > 20_000:
                raise ValueError("Visual action plan exceeded its limit")
        text = "".join(parts).strip()
        if text.startswith("```") and text.endswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip()
        return VisualPlanResponse.model_validate(json.loads(text))

    @staticmethod
    def _resolve_action(
        proposal: ProposedVisualAction,
        observation_id: str,
        visual: VisualUnderstanding,
    ) -> DesktopInputRequest:
        target = None
        if proposal.target_id:
            target = next((item for item in visual.targets if item.id == proposal.target_id), None)
            if target is None:
                raise ValueError("The proposed target is not present in the current observation")
            if target.confidence < 0.80:
                raise ValueError("Target confidence is too low for an input action")
            if not target.interactable and proposal.action not in {"move", "scroll"}:
                raise ValueError("The proposed target is not marked interactable")
        kwargs: dict[str, Any] = {
            "action": proposal.action,
            "amount": proposal.amount,
            "text": proposal.text,
            "key": proposal.key,
            "keys": proposal.keys,
            "target_label": target.label if target else None,
            "target_hwnd": (
                visual.active_window.hwnd
                if visual.active_window
                else None
            ),
        }
        # The structured visual model intentionally stores normalized boxes.
        # Pointer coordinates are derived here, never copied from the model.
        if target and target.bounds:
            kwargs["x"] = round((target.bounds.x + target.bounds.width / 2) * visual.screen_width)
            kwargs["y"] = round((target.bounds.y + target.bounds.height / 2) * visual.screen_height)
        return DesktopInputRequest.model_validate({key: value for key, value in kwargs.items() if value is not None})

    @staticmethod
    def _verify(
        before: VisualUnderstanding,
        after: VisualUnderstanding,
        expectation: VisualVerificationExpectation,
    ) -> dict[str, Any]:
        visible = {text.casefold() for text in after.visible_text}
        labels = {target.label.casefold() for target in after.targets}
        combined = visible | labels
        expected_text = [item for item in expectation.visible_text_contains if item.casefold() not in combined]
        title = after.active_window.title if after.active_window else ""
        process = after.active_window.process_name if after.active_window else ""
        title_ok = not expectation.active_window_title_contains or expectation.active_window_title_contains.casefold() in title.casefold()
        process_ok = not expectation.active_window_process_name or expectation.active_window_process_name.casefold() == process.casefold()
        changed = before.model_dump(mode="json") != after.model_dump(mode="json")
        success = not expected_text and title_ok and process_ok and (changed or bool(expectation.visible_text_contains))
        return {
            "success": success,
            "changed": changed,
            "missing_visible_text": expected_text,
            "active_window_title_ok": title_ok,
            "active_window_process_ok": process_ok,
        }

    async def _run(self, run_id: str) -> None:
        state = self._states[run_id]
        control = self._controls[run_id]
        vision_client = build_ollama_client(
            self.settings.ollama_base_url,
            self.settings.ollama_model,
            self.settings.request_timeout_seconds,
        )
        started = time.monotonic()
        try:
            if control.cancel_event.is_set():
                self._set_status(run_id, "cancelled")
                return
            current = await self._observe(run_id, vision_client)
            if current is None:
                self._set_status(run_id, "failed")
                return
            while True:
                allowed, was_paused = await self._wait_for_control(run_id)
                if not allowed:
                    return
                if was_paused:
                    current = await self._observe(run_id, vision_client)
                    if current is None:
                        self._set_status(run_id, "failed")
                        return
                    continue
                if time.monotonic() - started > state["max_duration_seconds"]:
                    self._set_status(run_id, "failed", "Visual task duration limit reached")
                    return
                if state["action_count"] >= state["max_actions"]:
                    self._set_status(run_id, "failed", "Visual task action limit reached")
                    return
                observation_id, visual = current
                pending_approval_id = state.get("approval_id")
                if pending_approval_id and state.get("pending_action"):
                    if visual.model_dump(mode="json") != state.get("pending_visual"):
                        self._set_status(
                            run_id,
                            "needs_clarification",
                            "Screen changed while approval was pending; the approval was not reused",
                        )
                        state["approval_id"] = None
                        self._persist_state(run_id)
                        return
                    request = DesktopInputRequest.model_validate(state["pending_action"])
                    self._set_status(run_id, "running")
                    result: ToolResult = await self.executor.execute(
                        "windows_input_action",
                        request.model_dump(exclude_none=True),
                        ToolContext(self.settings, self.database, None, None),
                        approval_id=str(pending_approval_id),
                    )
                    if result.status != "succeeded":
                        if result.status == "approval_required":
                            self._set_status(run_id, "waiting_approval")
                        else:
                            self._set_status(
                                run_id,
                                "failed",
                                result.error or "Approved input action failed",
                            )
                        return
                    state["action_count"] += 1
                    after = await self._observe(run_id, vision_client)
                    if after is None:
                        self._set_status(run_id, "failed")
                        return
                    verification = self._verify(
                        visual,
                        after[1],
                        VisualVerificationExpectation.model_validate(state.get("pending_verification") or {}),
                    )
                    state["latest_verification"] = verification
                    self._record_action(
                        run_id,
                        state["current_action"],
                        "verified" if verification["success"] else "unverified",
                        verification=verification,
                    )
                    state["current_action"] = None
                    state["approval_id"] = None
                    state.pop("pending_action", None)
                    state.pop("pending_visual", None)
                    state.pop("pending_verification", None)
                    self._persist_state(run_id)
                    if not verification["success"]:
                        state["consecutive_failures"] += 1
                        if state["consecutive_failures"] >= state["max_consecutive_failures"]:
                            self._set_status(run_id, "failed", "Visual verification failed repeatedly")
                            return
                    else:
                        state["consecutive_failures"] = 0
                    current = after
                    continue
                self._set_status(run_id, "planning")
                try:
                    plan = await self._plan(state["task"], observation_id, visual)
                except Exception as exc:
                    self._set_status(run_id, "failed", f"Visual planning failed: {exc}")
                    return
                if plan.observation_id != observation_id:
                    self._set_status(run_id, "needs_clarification", "Planner returned a stale observation id")
                    return
                if plan.done:
                    state["latest_verification"] = {"success": True, "reason": plan.reason}
                    self._set_status(run_id, "succeeded")
                    return
                if plan.action is None:
                    self._set_status(
                        run_id,
                        "needs_clarification",
                        plan.reason or "The visual planner needs clarification",
                    )
                    return
                try:
                    request = self._resolve_action(plan.action, observation_id, visual)
                except ValueError as exc:
                    self._set_status(run_id, "needs_clarification", str(exc))
                    return
                self._set_status(run_id, "running")
                state["current_action"] = request.model_dump(mode="json")
                state["current_action_sequence"] = state.get("next_action_sequence", 1)
                self._persist_state(run_id)
                result: ToolResult = await self.executor.execute(
                    "windows_input_action",
                    request.model_dump(exclude_none=True),
                    ToolContext(self.settings, self.database, None, None),
                )
                if result.status == "approval_required":
                    self._set_status(run_id, "waiting_approval")
                    state["approval_id"] = result.approval_id
                    state["pending_action"] = request.model_dump(mode="json")
                    state["pending_visual"] = visual.model_dump(mode="json")
                    state["pending_verification"] = plan.verification.model_dump(mode="json")
                    return
                if result.status != "succeeded":
                    state["consecutive_failures"] += 1
                    self._record_action(
                        run_id,
                        state["current_action"],
                        "failed",
                        error=result.error,
                    )
                    if state["consecutive_failures"] >= state["max_consecutive_failures"]:
                        self._set_status(
                            run_id,
                            "failed",
                            result.error or "Input action failed repeatedly",
                        )
                        return
                    current = await self._observe(run_id, vision_client)
                    if current is None:
                        self._set_status(run_id, "failed")
                        return
                    continue
                state["action_count"] += 1
                after = await self._observe(run_id, vision_client)
                if after is None:
                    self._set_status(run_id, "failed")
                    return
                verification = self._verify(visual, after[1], plan.verification)
                state["latest_verification"] = verification
                self._record_action(
                    run_id,
                    state["current_action"],
                    "verified" if verification["success"] else "unverified",
                    verification=verification,
                )
                state["current_action"] = None
                self._persist_state(run_id)
                if verification["success"]:
                    state["consecutive_failures"] = 0
                else:
                    state["consecutive_failures"] += 1
                    if state["consecutive_failures"] >= state["max_consecutive_failures"]:
                        self._set_status(run_id, "failed", "Visual verification failed repeatedly")
                        return
                current = after
        except asyncio.CancelledError:
            # An explicit user cancellation sets the control event first. A
            # runner cancellation without that event is normally process
            # shutdown; preserve it for restart review instead of claiming
            # that the task was intentionally cancelled or replaying it.
            if control.cancel_event.is_set():
                self._set_status(run_id, "cancelled")
            else:
                state["recovery_required"] = True
                self._set_status(
                    run_id,
                    "paused",
                    "Interrupted during restart; action outcome is unknown and requires review.",
                )
            raise
        except Exception as exc:
            self._set_status(run_id, "failed", f"Visual execution failed: {exc}")
        finally:
            self._persist_state(run_id)
            await vision_client.aclose()
