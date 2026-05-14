"""Tests for the text_to_speech tool."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from openjarvis.core.registry import ToolRegistry
from openjarvis.speech.tts import TTSResult
from openjarvis.speech.voice_runtime import TTSExecution, VoiceSelection


def test_tts_tool_registered():
    from openjarvis.tools.text_to_speech import TextToSpeechTool

    ToolRegistry.register_value("text_to_speech", TextToSpeechTool)
    assert ToolRegistry.contains("text_to_speech")


def test_tts_tool_execute(tmp_path):
    from openjarvis.tools.text_to_speech import TextToSpeechTool

    tool = TextToSpeechTool()
    mock_result = TTSExecution(
        selection=VoiceSelection(
            provider="cartesia",
            fallback_provider="openai_tts",
            voice_profile="jarvis_core",
            voice_id="jarvis",
            speed=1.0,
        ),
        results=[
            TTSResult(
                audio=b"fake-audio-data",
                format="mp3",
                voice_id="jarvis",
                duration_seconds=2.5,
            )
        ],
        metrics={"fallback_used": False, "ttfs_ms": 12.0, "total_synthesis_ms": 45.0},
    )

    with (
        patch("openjarvis.tools.text_to_speech.load_config", return_value=SimpleNamespace(speech=SimpleNamespace())),
        patch("openjarvis.tools.text_to_speech.TTSRegistry.contains", return_value=True),
        patch("openjarvis.tools.text_to_speech.synthesize_with_fallback", return_value=mock_result),
    ):
        result = tool.execute(
            text="Good morning sir.",
            voice_id="jarvis",
            backend="cartesia",
            output_dir=str(tmp_path),
        )

    assert result.success is True
    assert "digest.mp3" in result.content
    assert (tmp_path / "digest.mp3").exists()
    assert (tmp_path / "digest.mp3").read_bytes() == b"fake-audio-data"


def test_tts_tool_empty_text():
    from openjarvis.tools.text_to_speech import TextToSpeechTool

    tool = TextToSpeechTool()
    result = tool.execute(text="")
    assert result.success is False


def test_tts_tool_incremental(tmp_path):
    from openjarvis.tools.text_to_speech import TextToSpeechTool

    tool = TextToSpeechTool()
    mock_result = TTSExecution(
        selection=VoiceSelection(
            provider="cartesia",
            fallback_provider="openai_tts",
            voice_profile="briefing",
            voice_id="jarvis",
            speed=1.0,
        ),
        results=[
            TTSResult(
                audio=b"chunk",
                format="mp3",
                voice_id="jarvis",
                duration_seconds=1.0,
            ),
            TTSResult(
                audio=b"chunk",
                format="mp3",
                voice_id="jarvis",
                duration_seconds=1.0,
            ),
        ],
        metrics={"fallback_used": False, "ttfs_ms": 10.0, "total_synthesis_ms": 30.0},
    )

    with (
        patch("openjarvis.tools.text_to_speech.load_config", return_value=SimpleNamespace(speech=SimpleNamespace())),
        patch("openjarvis.tools.text_to_speech.TTSRegistry.contains", return_value=True),
        patch("openjarvis.tools.text_to_speech.synthesize_with_fallback", return_value=mock_result),
    ):
        result = tool.execute(
            text="A. B.",
            backend="cartesia",
            output_dir=str(tmp_path),
            incremental=True,
            max_chunk_chars=4,
        )

    assert result.success is True
    assert result.metadata["incremental"] is True
    assert len(result.metadata["audio_paths"]) == 2
    assert result.metadata["voice_profile"] == "briefing"
