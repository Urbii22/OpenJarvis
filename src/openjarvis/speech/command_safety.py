"""Pre-execution safety policy for voice commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from openjarvis.speech.semantic_router import CommandRouteResult
from openjarvis.tools.computer_use_policy import classify_computer_action

LOW_CONFIDENCE_THRESHOLD = 0.70
HIGH_CONFIDENCE_THRESHOLD = 0.90

DIRECT_EXECUTION_BLOCKED_TOOLS = frozenset(
    {
        "delete_path",
        "move_path",
        "copy_path",
        "shell_exec",
    }
)

DESTRUCTIVE_TOOLS = frozenset(
    {
        "delete_path",
        "move_path",
        "copy_path",
        "shell_exec",
    }
)

LOW_RISK_INTENTS = frozenset(
    {
        "app.open",
        "system.volume_up",
        "system.volume_down",
        "system.volume_mute",
        "system.volume_set",
        "media.play_pause",
        "media.next",
        "media.previous",
        "folder.open",
        "folder.search",
        "file.search",
    }
)


@dataclass(frozen=True, slots=True)
class CommandSafetyDecision:
    allow_execution: bool
    requires_confirmation: bool
    blocked: bool
    reason: str
    risk_level: str


def evaluate_command_safety(
    route: CommandRouteResult,
    *,
    tool_name: str | None = None,
    tool_params: Mapping[str, Any] | None = None,
) -> CommandSafetyDecision:
    normalized_tool = (tool_name or "").strip()
    params = dict(tool_params or {})

    if route.confidence < LOW_CONFIDENCE_THRESHOLD:
        return _blocked("low_confidence", "blocked")

    if normalized_tool in DIRECT_EXECUTION_BLOCKED_TOOLS:
        return _blocked("direct_execution_blocked", "blocked")

    risk_level = _risk_level(route=route, tool_name=normalized_tool, tool_params=params)
    if risk_level == "blocked":
        return _blocked("blocked_by_tool_policy", risk_level)

    if normalized_tool in DESTRUCTIVE_TOOLS:
        return _confirm("destructive_action_requires_confirmation", risk_level)

    if route.confidence < HIGH_CONFIDENCE_THRESHOLD:
        return _confirm("requires_confirmation_by_confidence", risk_level)

    if risk_level != "low":
        return _confirm("high_confidence_requires_low_risk", risk_level)

    return CommandSafetyDecision(
        allow_execution=True,
        requires_confirmation=False,
        blocked=False,
        reason="allowed",
        risk_level=risk_level,
    )


def _risk_level(
    *,
    route: CommandRouteResult,
    tool_name: str,
    tool_params: dict[str, Any],
) -> str:
    if tool_name:
        return classify_computer_action(tool_name, tool_params).level
    if route.intent in LOW_RISK_INTENTS:
        return "low"
    return "medium"


def _blocked(reason: str, risk_level: str) -> CommandSafetyDecision:
    return CommandSafetyDecision(
        allow_execution=False,
        requires_confirmation=True,
        blocked=True,
        reason=reason,
        risk_level=risk_level,
    )


def _confirm(reason: str, risk_level: str) -> CommandSafetyDecision:
    return CommandSafetyDecision(
        allow_execution=False,
        requires_confirmation=True,
        blocked=False,
        reason=reason,
        risk_level=risk_level,
    )
