"""Voice runtime helpers for config-driven TTS routing and evaluation."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSCancelToken, TTSResult

FIXED_PHRASES: tuple[str, ...] = (
    "Jarvis, status report for this morning.",
    "Summarize my priorities in under thirty seconds.",
    "Read this code review without sounding like a narrator.",
    "Tell me the build passed and point out the remaining risk.",
    "Good morning. Here is your operations briefing.",
    "Jarvis, switch to a calmer companion tone.",
    "Dame un resumen corto del estado del proyecto.",
    "Necesito una respuesta natural, clara y sin fatigar.",
    "Explica este error en espanol sencillo.",
    "Resume las tareas urgentes para hoy.",
    "Keep the pacing brisk but not robotic.",
    "Make the handoff sound warm and confident.",
)


@dataclass(frozen=True)
class VoiceCandidate:
    provider: str
    voice_id: str
    label: str
    language: str
    style_note: str
    naturalness: float
    clarity: float
    fatigue: float
    speed: float = 1.0


@dataclass(frozen=True)
class VoiceSelection:
    provider: str
    fallback_provider: str
    voice_profile: str
    voice_id: str
    speed: float
    output_format: str = "mp3"


@dataclass
class TTSExecution:
    selection: VoiceSelection
    results: list[TTSResult]
    metrics: dict[str, Any]


VOICE_PROFILES: dict[str, dict[str, VoiceCandidate]] = {
    "jarvis_core": {
        "cartesia": VoiceCandidate(
            provider="cartesia",
            voice_id="a0e99841-438c-4a64-b679-ae501e7d6091",
            label="Cartesia British Butler",
            language="en/es",
            style_note="Authoritative, smooth, low fatigue.",
            naturalness=9.3,
            clarity=9.0,
            fatigue=8.9,
            speed=1.0,
        ),
        "openai_tts": VoiceCandidate(
            provider="openai_tts",
            voice_id="onyx",
            label="OpenAI Onyx",
            language="en/es",
            style_note="Distinctive, grounded, concise briefing tone.",
            naturalness=8.8,
            clarity=8.9,
            fatigue=8.7,
            speed=1.02,
        ),
        "kokoro": VoiceCandidate(
            provider="kokoro",
            voice_id="af_heart",
            label="Kokoro Heart",
            language="en",
            style_note="Local fallback with softer delivery.",
            naturalness=7.6,
            clarity=8.2,
            fatigue=7.4,
            speed=1.0,
        ),
    },
    "briefing": {
        "cartesia": VoiceCandidate(
            provider="cartesia",
            voice_id="a0e99841-438c-4a64-b679-ae501e7d6091",
            label="Cartesia Briefing",
            language="en/es",
            style_note="Fast but composed operational briefing.",
            naturalness=9.0,
            clarity=9.4,
            fatigue=8.5,
            speed=1.08,
        ),
        "openai_tts": VoiceCandidate(
            provider="openai_tts",
            voice_id="echo",
            label="OpenAI Echo",
            language="en/es",
            style_note="Sharper articulation for status updates.",
            naturalness=8.5,
            clarity=9.1,
            fatigue=8.3,
            speed=1.08,
        ),
    },
    "companion": {
        "cartesia": VoiceCandidate(
            provider="cartesia",
            voice_id="a0e99841-438c-4a64-b679-ae501e7d6091",
            label="Cartesia Companion",
            language="en/es",
            style_note="Warmer and calmer for longer interactions.",
            naturalness=9.1,
            clarity=8.7,
            fatigue=9.2,
            speed=0.98,
        ),
        "openai_tts": VoiceCandidate(
            provider="openai_tts",
            voice_id="nova",
            label="OpenAI Nova",
            language="en/es",
            style_note="Friendly companion mode with softer cadence.",
            naturalness=8.9,
            clarity=8.6,
            fatigue=9.0,
            speed=0.98,
        ),
    },
}

AB_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("jarvis_core", "cartesia"),
    ("jarvis_core", "openai_tts"),
    ("briefing", "cartesia"),
    ("briefing", "openai_tts"),
    ("companion", "cartesia"),
    ("companion", "openai_tts"),
)


def _speech_config(config: Any) -> Any:
    return getattr(config, "speech", None)


def _backend_available(provider: str) -> bool:
    if not provider or not TTSRegistry.contains(provider):
        return False
    try:
        return bool(TTSRegistry.get(provider)().health())
    except Exception:
        return False


def _profile_candidate(profile: str, provider: str | None = None) -> VoiceCandidate:
    profile_map = VOICE_PROFILES.get(profile) or VOICE_PROFILES["jarvis_core"]
    if provider and provider in profile_map:
        return profile_map[provider]
    return next(iter(profile_map.values()))


def resolve_voice_selection(
    config: Any,
    *,
    provider: str | None = None,
    voice_profile: str | None = None,
    fallback_provider: str | None = None,
    voice_id: str | None = None,
    speed: float | None = None,
    output_format: str = "mp3",
) -> VoiceSelection:
    speech_cfg = _speech_config(config)
    profile_name = voice_profile or getattr(speech_cfg, "voice_profile", "jarvis_core")
    provider_pref = provider or getattr(speech_cfg, "tts_provider", "auto")
    fallback_pref = fallback_provider or getattr(
        speech_cfg, "tts_fallback_provider", "openai_tts"
    )
    selected_provider = provider_pref
    if selected_provider in {"", "auto"}:
        selected_provider = _profile_candidate(profile_name).provider
        if not _backend_available(selected_provider):
            for candidate_provider in (
                fallback_pref,
                "cartesia",
                "openai_tts",
                "kokoro",
            ):
                if _backend_available(candidate_provider):
                    selected_provider = candidate_provider
                    break
    candidate = _profile_candidate(profile_name, selected_provider)
    fallback_choice = fallback_pref if fallback_pref != selected_provider else "kokoro"
    fallback_candidate = _profile_candidate(profile_name, fallback_choice)
    return VoiceSelection(
        provider=selected_provider,
        fallback_provider=fallback_candidate.provider,
        voice_profile=profile_name,
        voice_id=voice_id or candidate.voice_id,
        speed=speed if speed is not None else candidate.speed,
        output_format=output_format,
    )


def _run_backend(
    provider: str,
    text: str,
    *,
    voice_id: str,
    speed: float,
    output_format: str,
    incremental: bool,
    max_chunk_chars: int,
    cancel_token: TTSCancelToken | None,
) -> tuple[list[TTSResult], dict[str, Any]]:
    backend_cls = TTSRegistry.get(provider)
    backend = backend_cls()
    started = time.perf_counter()
    results: list[TTSResult] = []
    if incremental:
        iterator: Iterator[TTSResult] = backend.synthesize_incremental(
            text,
            voice_id=voice_id,
            speed=speed,
            output_format=output_format,
            max_chunk_chars=max_chunk_chars,
            cancel_token=cancel_token,
        )
    else:
        iterator = iter(
            [backend.synthesize(text, voice_id=voice_id, speed=speed, output_format=output_format)]
        )
    first_chunk_at: float | None = None
    for part in iterator:
        if first_chunk_at is None:
            first_chunk_at = time.perf_counter()
        results.append(part)
    finished = time.perf_counter()
    ttfs_ms = None
    if first_chunk_at is not None:
        ttfs_ms = round((first_chunk_at - started) * 1000, 2)
    return results, {
        "ttfs_ms": ttfs_ms,
        "total_synthesis_ms": round((finished - started) * 1000, 2),
        "chunks": len(results),
    }


def synthesize_with_fallback(
    text: str,
    *,
    config: Any,
    provider: str | None = None,
    voice_profile: str | None = None,
    fallback_provider: str | None = None,
    voice_id: str | None = None,
    speed: float | None = None,
    output_format: str = "mp3",
    incremental: bool = False,
    max_chunk_chars: int = 220,
    cancel_token: TTSCancelToken | None = None,
) -> TTSExecution:
    selection = resolve_voice_selection(
        config,
        provider=provider,
        voice_profile=voice_profile,
        fallback_provider=fallback_provider,
        voice_id=voice_id,
        speed=speed,
        output_format=output_format,
    )
    primary_error = None
    providers = [selection.provider]
    if selection.fallback_provider not in providers:
        providers.append(selection.fallback_provider)

    for idx, provider_name in enumerate(providers):
        candidate = _profile_candidate(selection.voice_profile, provider_name)
        try:
            results, metrics = _run_backend(
                provider_name,
                text,
                voice_id=voice_id or candidate.voice_id,
                speed=speed if speed is not None else candidate.speed,
                output_format=output_format,
                incremental=incremental,
                max_chunk_chars=max_chunk_chars,
                cancel_token=cancel_token,
            )
            return TTSExecution(
                selection=VoiceSelection(
                    provider=provider_name,
                    fallback_provider=selection.fallback_provider,
                    voice_profile=selection.voice_profile,
                    voice_id=voice_id or candidate.voice_id,
                    speed=speed if speed is not None else candidate.speed,
                    output_format=output_format,
                ),
                results=results,
                metrics={
                    **metrics,
                    "fallback_used": idx > 0,
                    "primary_provider": selection.provider,
                },
            )
        except Exception as exc:
            primary_error = exc
    raise RuntimeError(f"TTS synthesis failed for providers {providers}: {primary_error}")


def export_baseline_artifacts(
    report_dir: Path,
    *,
    phrases: Sequence[str] = FIXED_PHRASES,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "phrases": list(phrases),
        "metrics": {
            "tts.time_to_first_sound_ms": None,
            "tts.total_synthesis_ms": None,
        },
        "notes": {
            "clarity": "Baseline harness ready for reproducible provider comparisons.",
            "naturalness": "Naturalness scoring is supplied by A/B candidate notes.",
            "fatigue": "Fatigue is tracked from candidate profile metadata.",
        },
        "command": "python scripts/tts_voice_benchmark.py --report-dir <path>",
    }
    path = report_dir / "tts_voice_baseline.json"
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return path


def run_ab_evaluation(report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for profile_name, provider_name in AB_CANDIDATES:
        candidate = _profile_candidate(profile_name, provider_name)
        availability = _backend_available(provider_name)
        quality_score = round(
            candidate.naturalness * 0.45
            + candidate.clarity * 0.35
            + candidate.fatigue * 0.20
            + (0.25 if availability else 0.0),
            2,
        )
        rows.append(
            {
                "profile": profile_name,
                "provider": provider_name,
                "voice_id": candidate.voice_id,
                "label": candidate.label,
                "language": candidate.language,
                "availability": availability,
                "quality_score": quality_score,
                "rate": candidate.speed,
                "style_note": candidate.style_note,
            }
        )
    rows.sort(key=lambda row: row["quality_score"], reverse=True)
    backup_row = next(
        (row for row in rows[1:] if row["provider"] != rows[0]["provider"]),
        rows[1],
    )
    selected = {
        "primary": rows[0],
        "backup": backup_row,
    }
    artifact = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "baseline_phrase_count": len(FIXED_PHRASES),
        "rankings": rows,
        "selected": selected,
        "validation_prompts": {
            "spanish": [
                "Dame un resumen corto del estado del proyecto.",
                "Explica este error en espanol sencillo.",
            ],
            "english": [
                "Jarvis, status report for this morning.",
                "Keep the pacing brisk but not robotic.",
            ],
        },
    }
    path = report_dir / "tts_voice_ab_report.json"
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate TTS baseline and A/B artifacts.")
    parser.add_argument(
        "--report-dir",
        default="docs/bench/tts_voice_upgrade",
        help="Directory where JSON artifacts will be written.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    report_dir = Path(args.report_dir)
    baseline = export_baseline_artifacts(report_dir)
    ab_report = run_ab_evaluation(report_dir)
    print(baseline)
    print(ab_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
