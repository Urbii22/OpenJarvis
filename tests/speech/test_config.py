"""Tests for speech configuration."""

from openjarvis.core.config import JarvisConfig, SpeechConfig


def test_speech_config_defaults():
    cfg = SpeechConfig()
    assert cfg.backend == "auto"
    assert cfg.model == "base"
    assert cfg.language == ""
    assert cfg.device == "auto"
    assert cfg.compute_type == "float16"
    assert cfg.continuous_mode_enabled is False
    assert cfg.wake_word == "jarvis"
    assert cfg.barge_in_enabled is True
    assert cfg.memory_context_enabled is False
    assert cfg.partial_streaming_enabled is False
    assert cfg.stt_streaming_strategy == "chunked_fallback"
    assert cfg.tts_provider == "auto"
    assert cfg.voice_profile == "jarvis_core"
    assert cfg.tts_fallback_provider == "openai_tts"
    assert cfg.tts_streaming_enabled is False
    assert cfg.tts_chunk_chars == 220
    assert cfg.tts_incremental_enabled is False
    assert cfg.tts_interrupt_cancellation_enabled is False


def test_jarvis_config_has_speech():
    cfg = JarvisConfig()
    assert hasattr(cfg, "speech")
    assert isinstance(cfg.speech, SpeechConfig)
    assert cfg.speech.backend == "auto"


def test_jarvis_system_has_speech_backend():
    """JarvisSystem has a speech_backend attribute."""
    from openjarvis.system import JarvisSystem

    assert "speech_backend" in JarvisSystem.__dataclass_fields__
