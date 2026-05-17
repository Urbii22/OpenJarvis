from __future__ import annotations

from openjarvis.core.types import ToolResult
from openjarvis.speech.command_executor import CommandExecutor
from openjarvis.speech.semantic_router import CommandRouteResult


def _route(
    *,
    intent: str = "app.open",
    confidence: float = 0.95,
    requires_confirmation: bool = False,
    arguments: dict[str, object] | None = None,
) -> CommandRouteResult:
    return CommandRouteResult(
        intent=intent,  # type: ignore[arg-type]
        confidence=confidence,
        corrected_text="dummy command",
        arguments=arguments or {},
        requires_confirmation=requires_confirmation,
        source="semantic_router",
        allow_execution=not requires_confirmation,
    )


def test_executes_mapped_open_app_tool() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_execute(tool_name: str, params: dict[str, object]) -> ToolResult:
        calls.append((tool_name, params))
        return ToolResult(tool_name=tool_name, content="ok", success=True)

    executor = CommandExecutor(execute_tool=fake_execute)
    result = executor.execute(_route(arguments={"target": "notepad"}))

    assert result.status == "executed"
    assert result.tool_name == "open_application"
    assert result.tool_result is not None and result.tool_result.success is True
    assert calls == [("open_application", {"app": "notepad"})]


def test_does_not_execute_when_confirmation_required() -> None:
    called = False

    def fake_execute(_: str, __: dict[str, object]) -> ToolResult:
        nonlocal called
        called = True
        return ToolResult(tool_name="open_application", content="ok", success=True)

    executor = CommandExecutor(execute_tool=fake_execute)
    result = executor.execute(_route(requires_confirmation=True, arguments={"target": "notepad"}))

    assert result.status == "pending_confirmation"
    assert called is False


def test_does_not_execute_when_low_confidence() -> None:
    called = False

    def fake_execute(_: str, __: dict[str, object]) -> ToolResult:
        nonlocal called
        called = True
        return ToolResult(tool_name="open_application", content="ok", success=True)

    executor = CommandExecutor(execute_tool=fake_execute)
    result = executor.execute(_route(confidence=0.65, arguments={"target": "notepad"}))

    assert result.status == "blocked"
    assert result.reason == "low_confidence"
    assert called is False


def test_unknown_is_never_executed() -> None:
    called = False

    def fake_execute(_: str, __: dict[str, object]) -> ToolResult:
        nonlocal called
        called = True
        return ToolResult(tool_name="open_application", content="ok", success=True)

    executor = CommandExecutor(execute_tool=fake_execute)
    result = executor.execute(_route(intent="unknown", confidence=0.95))

    assert result.status == "unknown"
    assert called is False


def test_returns_controlled_stub_for_unsupported_intents() -> None:
    executor = CommandExecutor()

    volume = executor.execute(_route(intent="system.volume_up", confidence=0.95))
    media = executor.execute(_route(intent="media.play_pause", confidence=0.95))

    assert volume.status == "stub"
    assert volume.reason == "set_volume_not_supported"
    assert media.status == "stub"
    assert media.reason == "media_control_not_supported"
