"""Adapters to apply pre-execution safety policy to routed voice commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.speech.command_safety import evaluate_command_safety
from openjarvis.speech.semantic_router import CommandRouteResult


def apply_command_safety(
    route: CommandRouteResult,
    *,
    tool_name: str | None = None,
    tool_params: Mapping[str, Any] | None = None,
) -> CommandRouteResult:
    decision = evaluate_command_safety(
        route,
        tool_name=tool_name,
        tool_params=tool_params,
    )
    return CommandRouteResult(
        intent=route.intent,
        confidence=route.confidence,
        corrected_text=route.corrected_text,
        arguments=dict(route.arguments),
        requires_confirmation=decision.requires_confirmation,
        source=route.source,
        error=decision.reason if decision.blocked else route.error,
        allow_execution=decision.allow_execution,
    )


ExecutionStatus = Literal["executed", "pending_confirmation", "blocked", "unknown", "stub"]
ToolExecutor = Callable[[str, Mapping[str, Any]], ToolResult]


@dataclass(frozen=True, slots=True)
class CommandExecutionResult:
    status: ExecutionStatus
    route: CommandRouteResult
    tool_name: str | None = None
    tool_params: dict[str, Any] | None = None
    tool_result: ToolResult | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class _CommandAction:
    kind: Literal["tool", "stub", "unknown"]
    tool_name: str | None = None
    tool_params: dict[str, Any] | None = None
    reason: str | None = None


class CommandExecutor:
    def __init__(self, *, execute_tool: ToolExecutor | None = None) -> None:
        self._execute_tool = execute_tool or _default_execute_tool

    def execute(self, route: CommandRouteResult) -> CommandExecutionResult:
        action = _resolve_action(route)
        if action.kind == "unknown":
            return CommandExecutionResult(status="unknown", route=route, reason=action.reason or "unknown_intent")

        if action.kind == "stub":
            return CommandExecutionResult(status="stub", route=route, reason=action.reason or "not_supported")

        assert action.tool_name is not None
        params = action.tool_params or {}
        safe_route = apply_command_safety(route, tool_name=action.tool_name, tool_params=params)

        if route.requires_confirmation or safe_route.requires_confirmation or not safe_route.allow_execution:
            blocked_reasons = {"low_confidence", "direct_execution_blocked", "blocked_by_tool_policy"}
            status: ExecutionStatus = "blocked" if safe_route.error in blocked_reasons else "pending_confirmation"
            return CommandExecutionResult(
                status=status,
                route=safe_route,
                tool_name=action.tool_name,
                tool_params=params,
                reason=safe_route.error,
            )

        tool_result = self._execute_tool(action.tool_name, params)
        return CommandExecutionResult(
            status="executed",
            route=safe_route,
            tool_name=action.tool_name,
            tool_params=params,
            tool_result=tool_result,
        )


def _resolve_action(route: CommandRouteResult) -> _CommandAction:
    if route.intent == "unknown":
        return _CommandAction(kind="unknown", reason=route.error or "unknown_intent")

    if route.intent == "app.open":
        app = str(
            route.arguments.get("target")
            or route.arguments.get("app")
            or route.arguments.get("application")
            or ""
        ).strip()
        if not app:
            return _CommandAction(kind="stub", reason="open_app_missing_app")
        args = str(route.arguments.get("args") or "").strip()
        params: dict[str, Any] = {"app": app}
        if args:
            params["args"] = args
        return _CommandAction(kind="tool", tool_name="open_application", tool_params=params)

    if route.intent.startswith("system.volume_"):
        return _CommandAction(kind="stub", reason="set_volume_not_supported")

    if route.intent.startswith("media."):
        return _CommandAction(kind="stub", reason="media_control_not_supported")

    if route.intent in {"folder.search", "file.search"}:
        query = str(route.arguments.get("query") or route.corrected_text).strip()
        return _CommandAction(kind="tool", tool_name="find_files", tool_params={"query": query})

    if route.intent == "folder.open":
        path = str(route.arguments.get("path") or "").strip()
        if not path:
            return _CommandAction(kind="stub", reason="folder_open_missing_path")
        return _CommandAction(kind="tool", tool_name="open_path", tool_params={"path": path})

    return _CommandAction(kind="unknown", reason="unsupported_intent")


def _default_execute_tool(tool_name: str, params: Mapping[str, Any]) -> ToolResult:
    tool = ToolRegistry.create(tool_name)
    return tool.execute(**dict(params))
