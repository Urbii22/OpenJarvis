"""OpenAI TTS backend — cloud-based voice synthesis via OpenAI API."""

from __future__ import annotations

import os
from typing import Iterator, List, Optional

import httpx

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSBackend, TTSCancelToken, TTSResult, split_text_for_tts

_OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"


def _openai_tts_request(
    api_key: str,
    text: str,
    voice: str,
    model: str = "tts-1",
    speed: float = 1.0,
    response_format: str = "mp3",
) -> bytes:
    """Call the OpenAI TTS API and return raw audio bytes."""
    resp = httpx.post(
        _OPENAI_TTS_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "input": text,
            "voice": voice,
            "speed": speed,
            "response_format": response_format,
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.content


@TTSRegistry.register("openai_tts")
class OpenAITTSBackend(TTSBackend):
    """OpenAI TTS backend — cloud synthesis."""

    backend_id = "openai_tts"

    def __init__(self, *, api_key: str = "", model: str = "tts-1") -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "nova",
        speed: float = 1.0,
        output_format: str = "mp3",
    ) -> TTSResult:
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

        audio = _openai_tts_request(
            self._api_key,
            text,
            voice=voice_id,
            model=self._model,
            speed=speed,
            response_format=output_format,
        )

        return TTSResult(
            audio=audio,
            format=output_format,
            voice_id=voice_id,
            metadata={"backend": "openai_tts", "model": self._model},
        )

    def available_voices(self) -> List[str]:
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    def health(self) -> bool:
        return bool(self._api_key)

    def synthesize_incremental(
        self,
        text: str,
        *,
        voice_id: str = "nova",
        speed: float = 1.0,
        output_format: str = "mp3",
        max_chunk_chars: int = 220,
        cancel_token: Optional[TTSCancelToken] = None,
    ) -> Iterator[TTSResult]:
        for chunk in split_text_for_tts(text, max_chars=max_chunk_chars):
            if cancel_token is not None and cancel_token.is_cancelled:
                return
            yield self.synthesize(
                chunk,
                voice_id=voice_id,
                speed=speed,
                output_format=output_format,
            )
