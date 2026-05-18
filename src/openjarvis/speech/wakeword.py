"""Wake-word helpers for local voice sessions."""

from __future__ import annotations


class WakeWordDetector:
    """Text-based wake-word detector for MVP realtime voice mode."""

    def __init__(self, wake_word: str = "jarvis") -> None:
        self._wake_word = (wake_word or "").strip().lower()

    def detect(self, text: str) -> bool:
        if not self._wake_word:
            return True
        return self._wake_word in text.lower()

    def strip(self, text: str) -> str:
        if not self._wake_word:
            return text.strip()
        return text.lower().replace(self._wake_word, "", 1).strip(" ,.:;!?")

