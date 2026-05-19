from __future__ import annotations

import json
from types import SimpleNamespace

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSBackend, TTSResult
from openjarvis.speech.voice_runtime import (
    export_baseline_artifacts,
    resolve_voice_selection,
    run_ab_evaluation,
    synthesize_with_fallback,
)


class _HealthyBackend(TTSBackend):
    backend_id = "healthy"

    def __init__(self, *, label: str = "healthy") -> None:
        self._label = label

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "mp3",
    ) -> TTSResult:
        return TTSResult(
            audio=f"{self._label}:{text}".encode(),
            format=output_format,
            voice_id=voice_id,
        )

    def available_voices(self):
        return ["voice"]

    def health(self) -> bool:
        return True


class _BrokenBackend(_HealthyBackend):
    backend_id = "broken"

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "mp3",
    ) -> TTSResult:
        raise RuntimeError("boom")


def test_resolve_voice_selection_uses_profile_defaults():
    config = SimpleNamespace(
        speech=SimpleNamespace(
            tts_provider="auto",
            voice_profile="companion",
            tts_fallback_provider="openai_tts",
        )
    )
    selection = resolve_voice_selection(config)
    assert selection.voice_profile == "companion"
    assert selection.provider in {"cartesia", "openai_tts", "kokoro"}


def test_synthesize_with_fallback_uses_secondary_provider(monkeypatch):
    TTSRegistry.clear()
    TTSRegistry.register_value("cartesia", _BrokenBackend)
    TTSRegistry.register_value("openai_tts", _HealthyBackend)
    config = SimpleNamespace(
        speech=SimpleNamespace(
            tts_provider="cartesia",
            voice_profile="jarvis_core",
            tts_fallback_provider="openai_tts",
        )
    )

    execution = synthesize_with_fallback("hola", config=config)

    assert execution.selection.provider == "openai_tts"
    assert execution.metrics["fallback_used"] is True
    assert execution.results[0].audio == b"healthy:hola"


def test_benchmark_artifacts_are_written(tmp_path):
    baseline = export_baseline_artifacts(tmp_path)
    report = run_ab_evaluation(tmp_path)

    baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
    report_payload = json.loads(report.read_text(encoding="utf-8"))

    assert baseline_payload["phrases"]
    assert report_payload["rankings"]
    assert (
        report_payload["selected"]["primary"]["quality_score"]
        >= report_payload["selected"]["backup"]["quality_score"]
    )
