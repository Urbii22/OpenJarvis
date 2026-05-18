from __future__ import annotations

import argparse
import importlib.util
import io
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from openjarvis.speech.tts import TTSResult


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "windows_hotkey_voice.py"
    spec = importlib.util.spec_from_file_location("windows_hotkey_voice", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules.setdefault(
        "winsound",
        SimpleNamespace(
            PlaySound=lambda *args, **kwargs: None,
            SND_FILENAME=0,
            SND_ASYNC=0,
            SND_PURGE=0,
        ),
    )
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class _SpeechCfg:
    continuous_mode_enabled: bool = False
    wake_word: str = "jarvis"
    barge_in_enabled: bool = True
    memory_context_enabled: bool = False
    tts_provider: str = "openai_tts"
    voice_profile: str = "jarvis_core"
    tts_fallback_provider: str = ""
    tts_streaming_enabled: bool = False
    tts_chunk_chars: int = 220
    tts_interrupt_cancellation_enabled: bool = False


@dataclass
class _SessionsCfg:
    voice_identity_enabled: bool = False
    voice_local_user_id: str = "local-voice-user"
    voice_local_session_id: str = ""


@dataclass
class _Cfg:
    speech: _SpeechCfg
    sessions: _SessionsCfg = field(default_factory=_SessionsCfg)


class _JarvisStub:
    def __init__(self, config=None):
        self._config = config

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def list_models(self):
        return ["stub"]

    def ask(self, text, agent=None):
        return "ok"


def _args(continuous_mode: bool) -> argparse.Namespace:
    return argparse.Namespace(
        hotkey="ctrl+alt+j",
        max_seconds=5.0,
        min_seconds=0.25,
        sample_rate=16000,
        language="es",
        stt_model="tiny",
        agent="orchestrator",
        no_pc_tools=False,
        continuous_mode=continuous_mode,
        wake_word="jarvis",
        disable_barge_in=False,
        live_ui=False,
        plain_ui=False,
        theme="hacker",
    )


class _UiStub:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)


def _wav_bytes() -> bytes:
    with io.BytesIO() as buff:
        with wave.open(buff, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(b"\x00\x00" * 32)
        return buff.getvalue()


def test_main_does_not_start_continuous_by_default(monkeypatch):
    mod = _load_module()
    started = {"value": False}

    monkeypatch.setattr(mod, "_assert_dependencies", lambda: None)
    monkeypatch.setattr(mod, "load_config", lambda: _Cfg(speech=_SpeechCfg()))
    monkeypatch.setattr(mod, "Jarvis", _JarvisStub)
    monkeypatch.setattr(mod, "_message_loop", lambda cfg, lock: None)
    monkeypatch.setattr(mod, "_set_status", lambda state, detail="": None)
    monkeypatch.setattr(mod, "_start_continuous_mode", lambda cfg, lock: started.__setitem__("value", True))
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: _args(False))

    mod.main()
    assert started["value"] is False


def test_main_starts_continuous_when_flag_enabled(monkeypatch):
    mod = _load_module()
    started = {"value": False}

    monkeypatch.setattr(mod, "_assert_dependencies", lambda: None)
    monkeypatch.setattr(mod, "load_config", lambda: _Cfg(speech=_SpeechCfg(continuous_mode_enabled=True)))
    monkeypatch.setattr(mod, "Jarvis", _JarvisStub)
    monkeypatch.setattr(mod, "_message_loop", lambda cfg, lock: None)
    monkeypatch.setattr(mod, "_set_status", lambda state, detail="": None)
    monkeypatch.setattr(mod, "_start_continuous_mode", lambda cfg, lock: started.__setitem__("value", True))
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: _args(False))

    mod.main()
    assert started["value"] is True


def test_main_does_not_start_live_ui_by_default(monkeypatch):
    mod = _load_module()
    ui_started = {"value": False}

    class _UIStub:
        def __init__(self, mode, theme):
            pass

        def start(self):
            ui_started["value"] = True

        def stop(self):
            pass

    monkeypatch.setattr(mod, "_assert_dependencies", lambda: None)
    monkeypatch.setattr(mod, "load_config", lambda: _Cfg(speech=_SpeechCfg()))
    monkeypatch.setattr(mod, "Jarvis", _JarvisStub)
    monkeypatch.setattr(mod, "_message_loop", lambda cfg, lock: None)
    monkeypatch.setattr(mod, "_set_status", lambda state, detail="": None)
    monkeypatch.setattr(mod, "TerminalVoiceUI", _UIStub)
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: _args(False))

    mod.main()
    assert ui_started["value"] is False


def test_main_starts_plain_live_ui_when_flags_set(monkeypatch):
    mod = _load_module()
    ui_mode = {"value": None}

    class _UIStub:
        def __init__(self, mode, theme):
            ui_mode["value"] = (mode, theme)

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(mod, "_assert_dependencies", lambda: None)
    monkeypatch.setattr(mod, "load_config", lambda: _Cfg(speech=_SpeechCfg()))
    monkeypatch.setattr(mod, "Jarvis", _JarvisStub)
    monkeypatch.setattr(mod, "_message_loop", lambda cfg, lock: None)
    monkeypatch.setattr(mod, "_set_status", lambda state, detail="": None)
    monkeypatch.setattr(mod, "TerminalVoiceUI", _UIStub)

    def _parse_args(_):
        ns = _args(False)
        ns.live_ui = True
        ns.plain_ui = True
        ns.theme = "plain"
        return ns

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", _parse_args)

    mod.main()
    assert ui_mode["value"] == ("plain", "plain")


def test_speak_windows_uses_incremental_tts_and_emits_streaming_metrics(monkeypatch):
    mod = _load_module()
    ui = _UiStub()
    play_calls: list[bytes] = []
    synth_calls: list[tuple[str, bool, int, object]] = []

    perf_values = iter([10.0, 10.05, 10.11, 10.11, 10.11, 10.11])

    monkeypatch.setattr(
        mod,
        "load_config",
        lambda: _Cfg(
            speech=_SpeechCfg(
                tts_streaming_enabled=True,
                tts_chunk_chars=12,
                tts_interrupt_cancellation_enabled=True,
            )
        ),
    )
    monkeypatch.setattr(mod, "_voice_ui", ui)
    monkeypatch.setattr(
        mod,
        "resolve_voice_selection",
        lambda cfg: SimpleNamespace(provider="openai_tts", voice_profile="jarvis_core"),
    )
    monkeypatch.setattr(
        mod,
        "synthesize_with_fallback",
        lambda text, **kwargs: (
            synth_calls.append(
                (
                    text,
                    kwargs["incremental"],
                    kwargs["max_chunk_chars"],
                    kwargs["cancel_token"],
                )
            )
            or SimpleNamespace(
                selection=SimpleNamespace(provider="openai_tts", voice_profile="jarvis_core"),
                results=[
                    TTSResult(audio=_wav_bytes(), format="wav", voice_id="onyx"),
                    TTSResult(audio=_wav_bytes(), format="wav", voice_id="onyx"),
                ],
                metrics={"ttfs_ms": 50.0, "total_synthesis_ms": 110.0},
            )
        ),
    )
    monkeypatch.setattr(
        mod,
        "_play_tts_result",
        lambda result, stop_event=None: play_calls.append(result.audio),
        raising=False,
    )
    monkeypatch.setattr(mod.time, "perf_counter", lambda: next(perf_values))

    def _unexpected_popen(*args, **kwargs):
        raise AssertionError("PowerShell TTS path should not run when streaming is enabled")

    monkeypatch.setattr(mod.subprocess, "Popen", _unexpected_popen)

    mod._speak_windows("Hola mundo. Seguimos.")

    assert len(synth_calls) == 1
    text, incremental, chunk_chars, cancel_token = synth_calls[0]
    assert text == "Hola mundo. Seguimos."
    assert incremental is True
    assert chunk_chars == 12
    assert cancel_token is not None
    assert len(play_calls) == 2

    synth_events = [event for event in ui.events if event.state == "SYNTHESIZING"]
    assert synth_events
    event = synth_events[-1]
    assert event.voice_provider == "openai_tts"
    assert event.voice_profile == "jarvis_core"
    assert event.ttfs_ms is not None and event.ttfs_ms > 0
    assert event.total_synthesis_ms is not None
    assert event.total_synthesis_ms >= event.ttfs_ms


def test_speak_windows_handles_missing_streaming_flags_gracefully(monkeypatch):
    mod = _load_module()
    play_calls: list[bytes] = []
    synth_calls: list[tuple[str, bool, int]] = []

    class _SpeechCfgWithoutFlags:
        tts_provider = "openai_tts"
        voice_profile = "briefing"

    monkeypatch.setattr(
        mod,
        "load_config",
        lambda: SimpleNamespace(
            speech=_SpeechCfgWithoutFlags(),
            sessions=_SessionsCfg(),
        ),
    )
    monkeypatch.setattr(
        mod,
        "resolve_voice_selection",
        lambda cfg: SimpleNamespace(provider="openai_tts", voice_profile="briefing"),
    )
    monkeypatch.setattr(
        mod,
        "synthesize_with_fallback",
        lambda text, **kwargs: (
            synth_calls.append((text, kwargs["incremental"], kwargs["max_chunk_chars"]))
            or SimpleNamespace(
                selection=SimpleNamespace(provider="openai_tts", voice_profile="briefing"),
                results=[TTSResult(audio=_wav_bytes(), format="wav", voice_id="echo")],
                metrics={"ttfs_ms": 12.0, "total_synthesis_ms": 25.0},
            )
        ),
    )
    monkeypatch.setattr(
        mod,
        "_play_tts_result",
        lambda result, stop_event=None: play_calls.append(result.audio),
        raising=False,
    )

    def _unexpected_popen(*args, **kwargs):
        raise AssertionError("PowerShell TTS path should not run on the new TTS stack")

    monkeypatch.setattr(mod.subprocess, "Popen", _unexpected_popen)

    mod._speak_windows("Ruta sin flags nuevas")

    assert synth_calls == [("Ruta sin flags nuevas", False, 220)]
    assert len(play_calls) == 1


def test_stop_speaking_stops_audio_output_and_marks_interrupted(monkeypatch):
    mod = _load_module()
    ui = _UiStub()
    stop_calls: list[str] = []

    class _Proc:
        def terminate(self):
            stop_calls.append("terminate")

    mod._tts_process = _Proc()
    monkeypatch.setattr(mod, "_voice_ui", ui)
    monkeypatch.setattr(mod, "sd", SimpleNamespace(stop=lambda: stop_calls.append("sd.stop")))

    mod._stop_speaking()

    assert "sd.stop" in stop_calls
    assert any(event.state == "INTERRUPTED" for event in ui.events)
