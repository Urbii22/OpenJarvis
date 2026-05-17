import httpx

from openjarvis.core.config import SpeechConfig
from openjarvis.speech.semantic_router import (
    OllamaSemanticRouter,
    build_ollama_semantic_router,
)


def test_ollama_router_returns_semantic_route_on_valid_payload() -> None:
    def _fake_generate(*, host: str, model: str, timeout_s: float, prompt: str) -> str:
        assert host == "http://localhost:11434"
        assert model == "qwen3:4b"
        assert timeout_s == 2.5
        assert "open spotify" in prompt
        return (
            '{"intent":"app.open","confidence":0.93,"corrected_text":"open spotify",'
            '"arguments":{"target":"spotify"},"requires_confirmation":false,'
            '"allow_execution":true}'
        )

    router = OllamaSemanticRouter(
        generate=_fake_generate,
        host="http://localhost:11434",
        model="qwen3:4b",
        timeout_s=2.5,
    )

    result = router.route("open spotify")

    assert result.intent == "app.open"
    assert result.source == "semantic_router"
    assert result.arguments == {"target": "spotify"}
    assert result.allow_execution is True
    assert result.error is None


def test_ollama_router_invalid_json_falls_back_safely() -> None:
    router = OllamaSemanticRouter(generate=lambda **_: "not-json")

    result = router.route("set volume 20")

    assert result.intent == "unknown"
    assert result.source == "unknown"
    assert result.requires_confirmation is False
    assert result.allow_execution is False
    assert result.error == "semantic_router_invalid_json"


def test_ollama_router_timeout_or_network_error_falls_back_safely() -> None:
    def _raise_timeout(**_: object) -> str:
        raise httpx.TimeoutException("timeout")

    router = OllamaSemanticRouter(generate=_raise_timeout)
    result = router.route("pause music")

    assert result.intent == "unknown"
    assert result.source == "unknown"
    assert result.requires_confirmation is False
    assert result.allow_execution is False
    assert result.error == "semantic_router_unavailable"


def test_build_router_reads_model_and_timeout_from_speech_config() -> None:
    cfg = SpeechConfig(
        semantic_router_model="qwen3:4b",
        semantic_router_timeout_seconds=9.0,
    )

    router = build_ollama_semantic_router(cfg, host="http://localhost:11434")

    assert router.model == "qwen3:4b"
    assert router.timeout_s == 9.0


def test_build_router_respects_disabled_config() -> None:
    cfg = SpeechConfig(semantic_router_enabled=False)

    assert build_ollama_semantic_router(cfg) is None
