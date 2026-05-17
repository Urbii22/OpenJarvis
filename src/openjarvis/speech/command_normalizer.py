"""Utilities to normalize raw speech transcriptions into command text."""

from __future__ import annotations

import re
import unicodedata

_WAKE_WORD_PREFIXES = (
    "hola jarvis",
    "oye jarvis",
    "hey jarvis",
    "jarvis",
)

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize_command(text: str) -> str:
    """Normalize raw transcription text without changing semantic intent."""
    raw = (text or "").strip().lower()
    if not raw:
        return ""

    normalized = _strip_accents(raw)
    normalized = _PUNCT_RE.sub(" ", normalized)
    normalized = _SPACE_RE.sub(" ", normalized).strip()

    for wake_prefix in _WAKE_WORD_PREFIXES:
        if normalized.startswith(wake_prefix):
            normalized = normalized[len(wake_prefix) :].strip()
            break

    return _SPACE_RE.sub(" ", normalized).strip()
