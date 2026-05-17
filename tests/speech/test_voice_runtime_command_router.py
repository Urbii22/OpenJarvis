from __future__ import annotations

from openjarvis.core.types import ToolResult
from openjarvis.speech.realtime_session import (
    RealtimeSessionConfig,
    RealtimeVoiceSession,
)
from openjarvis.speech.semantic_router import CommandRouteResult
from openjarvis.speech.voice_runtime import VoiceCommandRuntime


class _SemanticRouterStub:
    def route(self, command: str) -> CommandRouteResult:
        return CommandRouteResult(
            intent="app.open",
            confidence=0.96,
            corrected_text="abre spotify",
            arguments={"target": "spotify"},
            requires_confirmation=False,
            source="semantic_router",
            allow_execution=True,
        )


class _ConfirmationRouterStub:
    def route(self, command: str) -> CommandRouteResult:
        return CommandRouteResult(
            intent="app.open",
            confidence=0.76,
            corrected_text=command,
            arguments={"target": "photos"},
            requires_confirmation=True,
            source="semantic_router",
            allow_execution=False,
        )


def _ok_tool(tool_name: str, params: dict[str, object]) -> ToolResult:
    return ToolResult(tool_name=tool_name, content=f"ok:{params}", success=True)


def test_runtime_emits_execution_event_for_local_rule():
    runtime = VoiceCommandRuntime(execute_tool=_ok_tool)
    events = runtime.process_transcript("open vscode")

    assert [event.kind for event in events] == ["recognition", "execution"]
    assert events[-1].payload["status"] == "executed"
    assert events[-1].payload["route"]["intent"] == "app.open"
    assert events[-1].payload["route"]["source"] == "local_rule"


def test_runtime_uses_semantic_fallback_for_unknown_local_route():
    runtime = VoiceCommandRuntime(
        semantic_router=_SemanticRouterStub(),
        execute_tool=_ok_tool,
    )
    events = runtime.process_transcript("abre spotifai")

    assert [event.kind for event in events] == ["recognition", "execution"]
    assert events[-1].payload["status"] == "executed"
    assert events[-1].payload["route"]["source"] == "semantic_router"
    assert events[-1].payload["route"]["arguments"] == {"target": "spotify"}


def test_runtime_emits_confirmation_for_pending_confirmation_route():
    runtime = VoiceCommandRuntime(
        semantic_router=_ConfirmationRouterStub(),
        execute_tool=_ok_tool,
    )
    events = runtime.process_transcript("open photos")

    assert [event.kind for event in events] == ["recognition", "confirmation"]
    assert events[-1].payload["status"] == "pending_confirmation"


def test_runtime_emits_unknown_event_for_unhandled_commands():
    runtime = VoiceCommandRuntime(execute_tool=_ok_tool)
    events = runtime.process_transcript("esto no corresponde a ningun comando")

    assert [event.kind for event in events] == ["recognition", "unknown"]
    assert events[-1].payload["status"] == "unknown"
    assert events[-1].payload["route"].get("error") is None


def test_runtime_emits_error_event_when_execution_raises():
    def _explode_tool(_tool_name: str, _params: dict[str, object]) -> ToolResult:
        raise RuntimeError("boom")

    runtime = VoiceCommandRuntime(execute_tool=_explode_tool)
    events = runtime.process_transcript("open vscode")

    assert [event.kind for event in events] == ["recognition", "error"]
    assert events[-1].payload["error"] == "boom"


def test_realtime_session_can_emit_runtime_events_without_breaking_consume():
    session = RealtimeVoiceSession(
        RealtimeSessionConfig(wake_word="jarvis", followup_timeout_s=30)
    )
    runtime = VoiceCommandRuntime(execute_tool=_ok_tool)

    should_process, cleaned = session.consume("jarvis open vscode")
    events = session.consume_runtime("jarvis open vscode", runtime)

    assert should_process is True
    assert cleaned == "open vscode"
    assert [event.kind for event in events] == ["recognition", "execution"]
