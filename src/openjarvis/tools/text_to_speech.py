"""Text-to-speech tool — synthesize text to audio via configurable TTS backend."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from openjarvis.core.config import load_config
from openjarvis.core.registry import ToolRegistry, TTSRegistry
from openjarvis.core.types import ToolResult
from openjarvis.speech.voice_runtime import synthesize_with_fallback
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("text_to_speech")
class TextToSpeechTool(BaseTool):
    """Synthesize text into spoken audio using a TTS backend."""

    tool_id = "text_to_speech"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="text_to_speech",
            description=(
                "Convert text to spoken audio. Returns the file path to the "
                "generated audio file."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to synthesize into speech.",
                    },
                    "voice_id": {
                        "type": "string",
                        "description": "Voice identifier for the TTS backend.",
                    },
                    "backend": {
                        "type": "string",
                        "description": "TTS backend (cartesia, kokoro, openai_tts).",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory to save the audio file.",
                    },
                    "incremental": {
                        "type": "boolean",
                        "description": "Enable incremental chunked synthesis.",
                    },
                    "max_chunk_chars": {
                        "type": "integer",
                        "description": "Character window per chunk for incremental TTS.",
                    },
                },
                "required": ["text"],
            },
            category="audio",
            timeout_seconds=120.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        # Ensure TTS backends are registered
        import openjarvis.speech  # noqa: F401

        text = params.get("text", "")
        voice_id = params.get("voice_id", "")
        backend_key = params.get("backend", "")
        output_dir = params.get("output_dir", "")
        speed = float(params.get("speed", 1.0))
        incremental = bool(params.get("incremental", False))
        max_chunk_chars = int(params.get("max_chunk_chars", 220))

        if not text:
            return ToolResult(
                tool_name="text_to_speech",
                content="No text provided.",
                success=False,
            )

        if backend_key and not TTSRegistry.contains(backend_key):
            return ToolResult(
                tool_name="text_to_speech",
                content=f"TTS backend '{backend_key}' not available.",
                success=False,
            )

        # Save to file
        if output_dir:
            out_dir = Path(output_dir)
        else:
            out_dir = Path(tempfile.mkdtemp(prefix="jarvis-tts-"))

        out_dir.mkdir(parents=True, exist_ok=True)
        execution = synthesize_with_fallback(
            text,
            config=load_config(),
            provider=backend_key or None,
            voice_profile=params.get("voice_profile"),
            voice_id=voice_id or None,
            speed=speed,
            incremental=incremental,
            max_chunk_chars=max_chunk_chars,
        )
        results = execution.results

        if not results:
            return ToolResult(
                tool_name="text_to_speech",
                content="Synthesis canceled before output.",
                success=False,
            )

        ext = results[0].format or "mp3"
        audio_paths = []
        for idx, result in enumerate(results, start=1):
            suffix = "" if len(results) == 1 else f".part{idx}"
            audio_path = out_dir / f"digest{suffix}.{ext}"
            result.save(audio_path)
            audio_paths.append(str(audio_path))

        return ToolResult(
            tool_name="text_to_speech",
            content=audio_paths[0],
            success=True,
            metadata={
                "audio_path": audio_paths[0],
                "audio_paths": audio_paths,
                "format": ext,
                "duration_seconds": sum(r.duration_seconds for r in results),
                "voice_id": execution.selection.voice_id,
                "backend": execution.selection.provider,
                "incremental": incremental,
                "voice_profile": execution.selection.voice_profile,
                "fallback_used": execution.metrics.get("fallback_used", False),
                "ttfs_ms": execution.metrics.get("ttfs_ms"),
                "total_synthesis_ms": execution.metrics.get("total_synthesis_ms"),
            },
        )
