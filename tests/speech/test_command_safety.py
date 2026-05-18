from openjarvis.speech.command_executor import apply_command_safety
from openjarvis.speech.command_safety import evaluate_command_safety
from openjarvis.speech.semantic_router import CommandRouteResult


def _route(*, confidence: float = 0.95, intent: str = "app.open") -> CommandRouteResult:
    return CommandRouteResult(
        intent=intent,  # type: ignore[arg-type]
        confidence=confidence,
        corrected_text="open chrome",
        arguments={},
        requires_confirmation=False,
        source="semantic_router",
        allow_execution=True,
    )


def test_blocks_when_confidence_below_threshold() -> None:
    decision = evaluate_command_safety(_route(confidence=0.69))
    assert decision.blocked is True
    assert decision.reason == "low_confidence"
    assert decision.allow_execution is False
    assert decision.requires_confirmation is True


def test_requires_confirmation_for_mid_confidence() -> None:
    decision = evaluate_command_safety(_route(confidence=0.75))
    assert decision.blocked is False
    assert decision.requires_confirmation is True
    assert decision.reason == "requires_confirmation_by_confidence"
    assert decision.allow_execution is False


def test_allows_high_confidence_only_for_low_risk() -> None:
    low_risk = evaluate_command_safety(_route(confidence=0.95))
    assert low_risk.allow_execution is True
    assert low_risk.risk_level == "low"

    high_risk = evaluate_command_safety(
        _route(confidence=0.95),
        tool_name="create_folder",
        tool_params={"path": "C:/temp/new-folder"},
    )
    assert high_risk.allow_execution is False
    assert high_risk.requires_confirmation is True
    assert high_risk.reason == "high_confidence_requires_low_risk"


def test_destructive_actions_always_require_confirmation() -> None:
    decision = evaluate_command_safety(
        _route(confidence=0.95),
        tool_name="delete_path",
        tool_params={"path": "C:/temp/file.txt"},
    )
    assert decision.blocked is True
    assert decision.reason == "direct_execution_blocked"


def test_blocks_direct_execution_for_move_copy_and_shell_like() -> None:
    for tool_name in ("move_path", "copy_path", "shell_exec"):
        decision = evaluate_command_safety(_route(confidence=0.95), tool_name=tool_name)
        assert decision.blocked is True
        assert decision.reason == "direct_execution_blocked"
        assert decision.allow_execution is False


def test_command_executor_hook_applies_decision_to_route() -> None:
    safe_route = apply_command_safety(_route(confidence=0.75))
    assert safe_route.requires_confirmation is True
    assert safe_route.allow_execution is False

    blocked_route = apply_command_safety(_route(confidence=0.95), tool_name="shell_exec")
    assert blocked_route.allow_execution is False
    assert blocked_route.requires_confirmation is True
    assert blocked_route.error == "direct_execution_blocked"
