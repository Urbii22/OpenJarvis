"""Abstract base classes and data types for text-to-speech backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class TTSResult:
    """Result of a text-to-speech synthesis."""

    audio: bytes
    format: str = "mp3"
    duration_seconds: float = 0.0
    voice_id: str = ""
    sample_rate: int = 24000
    metadata: Dict[str, Any] = field(default_factory=dict)

    def save(self, path: Path) -> Path:
        """Write audio bytes to a file and return the path."""
        path.write_bytes(self.audio)
        return path


class TTSCancelToken:
    """Thread-safe cancellation token for incremental synthesis."""

    def __init__(self) -> None:
        self._evt = Event()

    def cancel(self) -> None:
        self._evt.set()

    @property
    def is_cancelled(self) -> bool:
        return self._evt.is_set()


def split_text_for_tts(text: str, max_chars: int = 220) -> List[str]:
    """Chunk text by sentence-like boundaries with a char limit fallback."""
    normalized = " ".join(text.split())
    if not normalized:
        return []
    parts: List[str] = []
    current = ""
    for token in normalized.split(" "):
        candidate = f"{current} {token}".strip()
        if len(candidate) > max_chars and current:
            parts.append(current)
            current = token
        else:
            current = candidate
        if current.endswith((".", "!", "?")):
            parts.append(current)
            current = ""
    if current:
        parts.append(current)
    return parts


class TTSBackend(ABC):
    """Abstract base class for text-to-speech backends."""

    backend_id: str = ""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "mp3",
    ) -> TTSResult:
        """Synthesize text to audio."""

    @abstractmethod
    def available_voices(self) -> List[str]:
        """Return list of available voice IDs."""

    @abstractmethod
    def health(self) -> bool:
        """Check if the backend is ready."""

    def synthesize_incremental(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "mp3",
        max_chunk_chars: int = 220,
        cancel_token: Optional[TTSCancelToken] = None,
    ) -> Iterator[TTSResult]:
        """Default incremental synthesis: per-chunk synthesize()."""
        for chunk in split_text_for_tts(text, max_chars=max_chunk_chars):
            if cancel_token is not None and cancel_token.is_cancelled:
                return
            yield self.synthesize(
                chunk,
                voice_id=voice_id,
                speed=speed,
                output_format=output_format,
            )


__all__ = ["TTSBackend", "TTSResult", "TTSCancelToken", "split_text_for_tts"]
