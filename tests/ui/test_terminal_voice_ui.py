from __future__ import annotations

import io
import time

import pytest
from rich.console import Console

from openjarvis.ui import TerminalVoiceUI, VoiceUiEvent


def test_plain_ui_renders_events_in_order():
    out = io.StringIO()
    ui = TerminalVoiceUI(mode="plain", output=out)
    ui.start()
    ui.emit(VoiceUiEvent(state="LISTENING", detail="mic open"))
    ui.emit(VoiceUiEvent(state="THINKING", detail="querying"))
    time.sleep(0.15)
    ui.stop()

    rendered = out.getvalue()
    assert "[LISTENING]" in rendered
    assert "[THINKING]" in rendered
    assert rendered.index("[LISTENING]") < rendered.index("[THINKING]")


def test_rich_mode_falls_back_to_plain_when_rich_missing(monkeypatch):
    out = io.StringIO()
    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "rich" or name.startswith("rich."):
            raise ImportError("rich missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)
    ui = TerminalVoiceUI(mode="rich", output=out)
    assert ui.mode == "plain"


def test_event_buffer_is_capped():
    out = io.StringIO()
    ui = TerminalVoiceUI(mode="plain", output=out, max_events=5)
    ui.start()
    for i in range(9):
        ui.emit(VoiceUiEvent(state="LOG", detail=str(i)))
    time.sleep(0.2)
    ui.stop()

    events = ui.events
    assert len(events) == 5
    assert events[0].detail == "4"
    assert events[-1].detail == "8"


def test_plain_ui_renders_mic_peak():
    out = io.StringIO()
    ui = TerminalVoiceUI(mode="plain", output=out)
    ui.start()
    ui.emit(VoiceUiEvent(state="MIC", mic_rms=0.01, mic_peak=0.02))
    time.sleep(0.15)
    ui.stop()

    assert "mic_peak=0.02000" in out.getvalue()


def test_plain_ui_renders_voice_provider_profile_and_synthesis_timings():
    out = io.StringIO()
    ui = TerminalVoiceUI(mode="plain", output=out)
    ui.start()
    ui.emit(
        VoiceUiEvent(
            state="SYNTHESIZING",
            detail="building audio",
            voice_provider="openai",
            voice_profile="jarvis_core",
            ttfs_ms=87.3,
            total_synthesis_ms=412.8,
        )
    )
    time.sleep(0.15)
    ui.stop()

    rendered = out.getvalue()
    assert "[SYNTHESIZING]" in rendered
    assert "provider=openai" in rendered
    assert "profile=jarvis_core" in rendered
    assert "ttfs=87.3ms" in rendered
    assert "total_synthesis=412.8ms" in rendered


def test_rich_ui_keeps_synthesis_state_stable_during_mic_refresh():
    pytest.importorskip("rich")

    rich_out = io.StringIO()
    ui = TerminalVoiceUI(mode="rich", output=rich_out)
    ui._rich = Console(file=rich_out, record=True)

    ui._update_live_state(
        VoiceUiEvent(
            state="SYNTHESIZING",
            detail="assembling chunks",
            voice_provider="elevenlabs",
            voice_profile="companion",
            ttfs_ms=54.0,
            total_synthesis_ms=201.0,
        )
    )
    ui._update_live_state(VoiceUiEvent(state="MIC", mic_rms=0.01, mic_peak=0.02))
    layout = ui._build_layout()

    assert ui._last_state == "SYNTHESIZING"
    assert ui._last_voice_provider == "elevenlabs"
    assert ui._last_voice_profile == "companion"
    assert ui._last_ttfs_ms == 54.0
    assert ui._last_total_synthesis_ms == 201.0

    ui._rich.print(layout)
    rendered = ui._rich.export_text()
    assert "SYNTHESIZING" in rendered
    assert "elevenlabs" in rendered
    assert "companion" in rendered
    assert "54.0 ms" in rendered
    assert "201.0 ms" in rendered


def test_rich_ui_renders_interrupted_state():
    pytest.importorskip("rich")

    rich_out = io.StringIO()
    ui = TerminalVoiceUI(mode="rich", output=rich_out)
    ui._rich = Console(file=rich_out, record=True)
    ui._update_live_state(VoiceUiEvent(state="INTERRUPTED", detail="stop requested"))

    ui._rich.print(ui._build_layout())
    rendered = ui._rich.export_text()

    assert "INTERRUPTED" in rendered
    assert "stop requested" in rendered
