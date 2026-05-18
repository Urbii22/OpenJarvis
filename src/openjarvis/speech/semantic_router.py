"""Shared typed schema and local semantic routing for voice commands."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Literal

import httpx

if TYPE_CHECKING:
    from openjarvis.core.config import SpeechConfig

RouteIntent = Literal[
    "app.open",
    "system.volume_up",
    "system.volume_down",
    "system.volume_mute",
    "system.volume_set",
    "media.play_pause",
    "media.next",
    "media.previous",
    "folder.search",
    "folder.open",
    "file.search",
    "unknown",
]
RouteSource = Literal["local_rule", "semantic_router", "unknown"]

_ALLOWED_INTENTS: set[str] = {
    "app.open",
    "system.volume_up",
    "system.volume_down",
    "system.volume_mute",
    "system.volume_set",
    "media.play_pause",
    "media.next",
    "media.previous",
    "folder.search",
    "folder.open",
    "file.search",
    "unknown",
}
_ALLOWED_SOURCES: set[str] = {"local_rule", "semantic_router", "unknown"}
_SOURCE_ALIASES = {"local_rules": "local_rule", "semantic": "semantic_router", "fallback": "unknown"}
_DEFAULT_OLLAMA_HOST = "http://localhost:11434"
_DEFAULT_OLLAMA_MODEL = "qwen3:4b"
_DEFAULT_OLLAMA_TIMEOUT_S = 2.5


def _normalize_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    if confidence != confidence:  # NaN
        return 0.0
    return max(0.0, min(1.0, confidence))


@dataclass(slots=True, init=False)
class CommandRouteResult:
    """Safe shared result for voice command routing across layers."""

    intent: RouteIntent = "unknown"
    corrected_text: str = ""
    confidence: float = 0.0
    requires_confirmation: bool = False
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    source: RouteSource = "unknown"
    error: str | None = None
    allow_execution: bool = False

    def __init__(
        self,
        *,
        intent: str = "unknown",
        corrected_text: Any = "",
        confidence: Any = 0.0,
        requires_confirmation: Any = False,
        arguments: Any | None = None,
        reason: Any | None = None,
        source: str = "unknown",
        error: Any | None = None,
        allow_execution: Any = False,
        command: Any | None = None,
        slots: Any | None = None,
    ) -> None:
        # Backward-compatible aliases while the rest of the repo settles on
        # the planned corrected_text/arguments contract.
        if corrected_text == "" and command is not None:
            corrected_text = command
        if arguments is None and slots is not None:
            arguments = slots

        raw_intent = intent if isinstance(intent, str) else "unknown"
        normalized_intent = raw_intent if raw_intent in _ALLOWED_INTENTS else "unknown"
        confidence_value = _normalize_confidence(confidence)
        text_value = corrected_text.strip() if isinstance(corrected_text, str) else ""
        arguments_value = arguments if isinstance(arguments, dict) else {}
        raw_source = source if isinstance(source, str) else "unknown"
        aliased_source = _SOURCE_ALIASES.get(raw_source, raw_source)
        source_value = aliased_source if aliased_source in _ALLOWED_SOURCES else "unknown"
        reason_value = reason if isinstance(reason, str) and reason.strip() else None
        error_value = error if isinstance(error, str) and error.strip() else None
        requires_confirmation_value = bool(requires_confirmation)
        allow_execution_value = bool(allow_execution)

        invalid_payload = (
            raw_intent != normalized_intent
            or source_value != aliased_source
            or not isinstance(arguments, (dict, type(None)))
            or (corrected_text is not None and not isinstance(corrected_text, str))
        )

        if invalid_payload:
            normalized_intent = "unknown"
            source_value = "unknown"
            arguments_value = {}
            requires_confirmation_value = True
            allow_execution_value = False
            error_value = error_value or "invalid_route_input"

        if normalized_intent == "unknown":
            source_value = "unknown"
            allow_execution_value = False
            if not invalid_payload:
                requires_confirmation_value = False
        elif not text_value:
            normalized_intent = "unknown"
            source_value = "unknown"
            arguments_value = {}
            requires_confirmation_value = True
            allow_execution_value = False
            error_value = error_value or "invalid_route_input"
        elif confidence_value < 0.70:
            requires_confirmation_value = True
            allow_execution_value = False

        if requires_confirmation_value:
            allow_execution_value = False

        object.__setattr__(self, "intent", normalized_intent)
        object.__setattr__(self, "corrected_text", text_value)
        object.__setattr__(self, "confidence", confidence_value)
        object.__setattr__(self, "requires_confirmation", requires_confirmation_value)
        object.__setattr__(self, "arguments", arguments_value)
        object.__setattr__(self, "reason", reason_value)
        object.__setattr__(self, "source", source_value)
        object.__setattr__(self, "error", error_value)
        object.__setattr__(self, "allow_execution", allow_execution_value)

    @property
    def command(self) -> str:
        return self.corrected_text

    @property
    def slots(self) -> dict[str, Any]:
        return self.arguments

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "intent": self.intent,
            "corrected_text": self.corrected_text,
            "confidence": self.confidence,
            "requires_confirmation": self.requires_confirmation,
            "arguments": dict(self.arguments),
            "source": self.source,
            "allow_execution": self.allow_execution,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.error is not None:
            payload["error"] = self.error
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


SemanticGenerateFn = Callable[[str, str, float, str], str]


def _fallback_result(command: str, *, error: str) -> CommandRouteResult:
    return CommandRouteResult(
        intent="unknown",
        confidence=0.0,
        corrected_text=command,
        arguments={},
        requires_confirmation=False,
        source="unknown",
        error=error,
        allow_execution=False,
    )


def _default_ollama_generate(host: str, model: str, timeout_s: float, prompt: str) -> str:
    payload = {
        "model": model,
        "stream": False,
        "prompt": prompt,
        "format": "json",
        "options": {"temperature": 0.0},
    }
    with httpx.Client(base_url=host.rstrip("/"), timeout=timeout_s) as client:
        resp = client.post("/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()
    return str(data.get("response", ""))


@dataclass(slots=True)
class OllamaSemanticRouter:
    """Semantic router backed by local Ollama with safe degradation."""

    host: str = ""
    model: str = _DEFAULT_OLLAMA_MODEL
    timeout_s: float = _DEFAULT_OLLAMA_TIMEOUT_S
    generate: SemanticGenerateFn = _default_ollama_generate

    def route(self, command: str) -> CommandRouteResult:
        clean_command = command.strip() if isinstance(command, str) else ""
        if not clean_command:
            return _fallback_result("", error="semantic_router_empty_command")

        prompt = (
            "You are a strict local voice command semantic router. Return ONLY a JSON object "
            "with keys: intent, corrected_text, confidence, requires_confirmation, arguments, "
            "reason, allow_execution. Valid intent values: app.open, system.volume_up, "
            "system.volume_down, system.volume_mute, media.play_pause, media.next, "
            "media.previous, folder.search, folder.open, file.search, unknown. "
            "Do not invent actions. Use unknown when unsure. "
            f'User command: "{clean_command}"'
        )
        try:
            raw = self.generate(
                host=self._resolved_host(),
                model=self.model,
                timeout_s=self.timeout_s,
                prompt=prompt,
            )
        except Exception:
            return _fallback_result(clean_command, error="semantic_router_unavailable")

        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return _fallback_result(clean_command, error="semantic_router_invalid_json")
        if not isinstance(parsed, dict):
            return _fallback_result(clean_command, error="semantic_router_invalid_payload")

        if not {"intent", "confidence"}.issubset(parsed):
            return _fallback_result(clean_command, error="semantic_router_missing_fields")

        return CommandRouteResult(
            intent=parsed.get("intent", "unknown"),
            confidence=parsed.get("confidence", 0.0),
            corrected_text=parsed.get("corrected_text", parsed.get("command", clean_command)),
            arguments=parsed.get("arguments", parsed.get("slots", {})),
            requires_confirmation=parsed.get("requires_confirmation", True),
            source="semantic_router",
            reason=parsed.get("reason"),
            error=None,
            allow_execution=parsed.get("allow_execution", False),
        )

    def _resolved_host(self) -> str:
        host = self.host.strip()
        if host:
            return host
        env_host = os.environ.get("OLLAMA_HOST", "").strip()
        return env_host or _DEFAULT_OLLAMA_HOST


def build_ollama_semantic_router(
    speech_config: SpeechConfig,
    *,
    host: str = "",
    generate: SemanticGenerateFn = _default_ollama_generate,
) -> OllamaSemanticRouter | None:
    """Build a router from speech config with local-first Ollama defaults."""
    if not getattr(speech_config, "semantic_router_enabled", True):
        return None
    return OllamaSemanticRouter(
        host=host,
        model=getattr(speech_config, "semantic_router_model", _DEFAULT_OLLAMA_MODEL),
        timeout_s=getattr(speech_config, "semantic_router_timeout_seconds", _DEFAULT_OLLAMA_TIMEOUT_S),
        generate=generate,
    )
