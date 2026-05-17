import json

from openjarvis.speech.semantic_router import CommandRouteResult


def test_valid_route_is_kept_and_confidence_is_clamped():
    result = CommandRouteResult(
        intent="app.open",
        confidence=1.4,
        corrected_text="  open spotify  ",
        arguments={"target": "spotify"},
        requires_confirmation=False,
        source="local_rule",
        allow_execution=True,
    )

    assert result.intent == "app.open"
    assert result.confidence == 1.0
    assert result.corrected_text == "open spotify"
    assert result.arguments == {"target": "spotify"}
    assert result.allow_execution is True
    assert result.error is None


def test_invalid_input_degrades_to_safe_unknown():
    result = CommandRouteResult(
        intent="drop_database",  # type: ignore[arg-type]
        confidence="not-a-number",  # type: ignore[arg-type]
        corrected_text=None,  # type: ignore[arg-type]
        arguments=["bad"],  # type: ignore[arg-type]
        requires_confirmation=False,
        source="invalid",  # type: ignore[arg-type]
        allow_execution=True,
    )

    assert result.intent == "unknown"
    assert result.confidence == 0.0
    assert result.corrected_text == ""
    assert result.source == "unknown"
    assert result.arguments == {}
    assert result.requires_confirmation is True
    assert result.allow_execution is False
    assert result.error == "invalid_route_input"


def test_unknown_or_confirmation_never_allows_execution():
    unknown = CommandRouteResult(
        intent="unknown",
        confidence=0.9,
        corrected_text="something",
        requires_confirmation=False,
        allow_execution=True,
    )
    needs_confirmation = CommandRouteResult(
        intent="media.play_pause",
        confidence=0.9,
        corrected_text="pause",
        requires_confirmation=True,
        allow_execution=True,
    )

    assert unknown.allow_execution is False
    assert unknown.error is None
    assert unknown.source == "unknown"
    assert needs_confirmation.allow_execution is False


def test_json_serialization_is_clean_and_round_trippable():
    result = CommandRouteResult(
        intent="system.volume_up",
        confidence=0.55,
        corrected_text="sube el volumen",
        arguments={"direction": "up"},
        requires_confirmation=True,
        source="semantic_router",
        allow_execution=True,
    )

    as_dict = result.to_dict()
    encoded = result.to_json()
    decoded = json.loads(encoded)

    assert "error" not in as_dict
    assert decoded == as_dict
