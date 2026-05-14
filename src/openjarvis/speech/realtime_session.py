"""Minimal realtime voice session state machine for Phase A."""

from __future__ import annotations

import time
from dataclasses import dataclass

from openjarvis.speech.wakeword import WakeWordDetector


@dataclass(slots=True)
class RealtimeSessionConfig:
    wake_word: str = "jarvis"
    followup_timeout_s: float = 12.0


class RealtimeVoiceSession:
    """Tracks wake-word activation and follow-up turns."""

    def __init__(self, cfg: RealtimeSessionConfig) -> None:
        self._cfg = cfg
        self._wake = WakeWordDetector(cfg.wake_word)
        self._active_until = 0.0

    def _is_active(self) -> bool:
        return time.monotonic() < self._active_until

    def consume(self, text: str) -> tuple[bool, str]:
        raw = (text or "").strip()
        if not raw:
            return False, ""

        if self._wake.detect(raw):
            self._active_until = time.monotonic() + self._cfg.followup_timeout_s
            cleaned = self._wake.strip(raw)
            return bool(cleaned), cleaned

        if self._is_active():
            self._active_until = time.monotonic() + self._cfg.followup_timeout_s
            return True, raw

        return False, ""

