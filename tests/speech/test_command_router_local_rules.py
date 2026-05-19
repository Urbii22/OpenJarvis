from openjarvis.speech.command_router import route_command


def test_open_app_known_alias_is_high_confidence() -> None:
    result = route_command("abre vscode")
    assert result.intent == "app.open"
    assert result.arguments == {"target": "vscode"}
    assert result.source == "local_rule"
    assert result.confidence >= 0.90
    assert result.requires_confirmation is False
    assert result.allow_execution is True


def test_open_app_unknown_target_requires_confirmation() -> None:
    result = route_command("open photos")
    assert result.intent == "unknown"
    assert result.arguments == {"candidate_target": "photos"}
    assert 0.70 <= result.confidence < 0.90
    assert result.requires_confirmation is False
    assert result.allow_execution is False


def test_set_volume_absolute_percentage() -> None:
    result = route_command("set volume to 40%")
    assert result.intent == "system.volume_set"
    assert result.arguments == {"level": 40}
    assert result.confidence >= 0.90
    assert result.requires_confirmation is False
    assert result.allow_execution is True


def test_set_volume_ambiguous_direction() -> None:
    result = route_command("sube y baja el volumen")
    assert result.intent == "unknown"
    assert result.arguments == {"candidate_intents": ["system.volume_up", "system.volume_down"]}
    assert 0.70 <= result.confidence < 0.90
    assert result.requires_confirmation is False
    assert result.allow_execution is False


def test_media_control_next_is_high_confidence() -> None:
    result = route_command("next song")
    assert result.intent == "media.next"
    assert result.arguments == {}
    assert result.confidence >= 0.90
    assert result.requires_confirmation is False
    assert result.allow_execution is True


def test_unknown_command_falls_back_safely() -> None:
    result = route_command("what is the weather")
    assert result.intent == "unknown"
    assert result.source == "unknown"
    assert result.confidence < 0.70
    assert result.requires_confirmation is False
    assert result.allow_execution is False
    assert result.error is None


def test_unknown_app_target_can_fall_through_to_semantic_router() -> None:
    result = route_command("abre spotifai")

    assert result.intent == "unknown"
    assert result.arguments == {"candidate_target": "spotifai"}
    assert result.requires_confirmation is False
