"""Tests for speech ABC and data types."""

from openjarvis.speech._stubs import Segment, SpeechBackend, TranscriptionResult


def test_transcription_result():
    result = TranscriptionResult(
        text="Hello world",
        language="en",
        confidence=0.95,
        duration_seconds=1.5,
        segments=[],
    )
    assert result.text == "Hello world"
    assert result.language == "en"
    assert result.confidence == 0.95
    assert result.duration_seconds == 1.5
    assert result.segments == []


def test_segment():
    seg = Segment(text="Hello", start=0.0, end=0.5, confidence=0.98)
    assert seg.text == "Hello"
    assert seg.start == 0.0
    assert seg.end == 0.5


def test_speech_backend_is_abstract():
    import pytest

    with pytest.raises(TypeError):
        SpeechBackend()


def test_transcribe_stream_default_fallback():
    class _DummySpeech(SpeechBackend):
        backend_id = "dummy"

        def transcribe(self, audio: bytes, *, format: str = "wav", language=None):
            return TranscriptionResult(text="ok", language="en", confidence=0.9)

        def health(self) -> bool:
            return True

        def supported_formats(self):
            return ["wav"]

    backend = _DummySpeech()
    chunks = list(backend.transcribe_stream([b"a", b"b"], format="wav"))
    assert len(chunks) == 1
    assert chunks[0].is_final is True
    assert chunks[0].text == "ok"
