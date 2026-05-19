"""Deterministic local rules for obvious voice commands."""

from __future__ import annotations

import re

from .semantic_router import CommandRouteResult

_OPEN_PREFIX = re.compile(
    r"^(?:open|launch|start|run|abre|abrir|inicia|iniciar)\s+(?:la\s+|el\s+)?(?P<app>[a-z0-9][\w\-. ]{1,30})$",
    re.IGNORECASE,
)
_PERCENTAGE = re.compile(r"\b(\d{1,3})\s*%\b")
_ABSOLUTE_VOLUME = re.compile(r"\b(?:vol(?:ume|umen)?\s+(?:to|at|a|al)\s*)?(\d{1,3})\b")
_SPACE = re.compile(r"\s+")

_APP_ALIASES: dict[str, str] = {
    "vscode": "vscode",
    "visual studio code": "vscode",
    "vs code": "vscode",
    "code": "vscode",
    "spotify": "spotify",
    "chrome": "chrome",
    "google chrome": "chrome",
    "firefox": "firefox",
    "edge": "edge",
    "terminal": "terminal",
    "cmd": "cmd",
    "notepad": "notepad",
    "calculator": "calculator",
    "calculadora": "calculator",
}

_VOLUME_WORDS = ("volume", "volumen")
_VOLUME_UP = ("sube", "subir", "subirle", "incrementa", "aumenta", "up", "raise", "increase")
_VOLUME_DOWN = ("baja", "bajar", "down", "lower", "decrease")
_VOLUME_MUTE = ("mute", "mutear", "silence", "silenciar", "silencio")

_PLAY = ("play", "resume", "reproducir", "reanuda")
_PAUSE = ("pause", "pausa", "pausar")
_NEXT = ("next", "siguiente", "skip")
_PREVIOUS = ("previous", "prev", "anterior", "back")


def route_command(command: str) -> CommandRouteResult:
    text = _normalize(command)
    if not text:
        return _unknown(command)

    for router in (_route_open_app, _route_volume, _route_media):
        result = router(text, command)
        if result is not None:
            return result
    return _unknown(command)


def _route_open_app(text: str, command: str) -> CommandRouteResult | None:
    match = _OPEN_PREFIX.match(text)
    if not match:
        return None
    app_raw = _normalize(match.group("app")).strip(" .")
    if not app_raw:
        return _unknown(command)
    app = _APP_ALIASES.get(app_raw, app_raw)
    if app_raw not in _APP_ALIASES:
        return CommandRouteResult(
            intent="unknown",
            confidence=0.82,
            corrected_text=command,
            arguments={"candidate_target": app_raw},
            requires_confirmation=True,
            source="unknown",
            allow_execution=False,
        )
    return CommandRouteResult(
        intent="app.open",
        confidence=0.95,
        corrected_text=command,
        arguments={"target": app},
        requires_confirmation=False,
        source="local_rule",
        allow_execution=True,
    )


def _route_volume(text: str, command: str) -> CommandRouteResult | None:
    if not _contains_any(text, _VOLUME_WORDS):
        return None

    percentage_match = _PERCENTAGE.search(text)
    if percentage_match:
        level = int(percentage_match.group(1))
        if 0 <= level <= 100:
            return CommandRouteResult(
                intent="system.volume_set",
                confidence=0.96,
                corrected_text=command,
                arguments={"level": level},
                requires_confirmation=False,
                source="local_rule",
                allow_execution=True,
            )

    absolute_match = _ABSOLUTE_VOLUME.search(text)
    if absolute_match:
        level = int(absolute_match.group(1))
        if 0 <= level <= 100:
            return CommandRouteResult(
                intent="system.volume_set",
                confidence=0.93,
                corrected_text=command,
                arguments={"level": level},
                requires_confirmation=False,
                source="local_rule",
                allow_execution=True,
            )

    if _contains_any(text, _VOLUME_MUTE):
        return CommandRouteResult(
            intent="system.volume_mute",
            confidence=0.95,
            corrected_text=command,
            arguments={},
            requires_confirmation=False,
            source="local_rule",
            allow_execution=True,
        )

    go_up = _contains_any(text, _VOLUME_UP)
    go_down = _contains_any(text, _VOLUME_DOWN)
    if go_up and go_down:
        return CommandRouteResult(
            intent="unknown",
            confidence=0.75,
            corrected_text=command,
            arguments={"candidate_intents": ["system.volume_up", "system.volume_down"]},
            requires_confirmation=True,
            source="unknown",
            allow_execution=False,
        )
    if go_up or go_down:
        return CommandRouteResult(
            intent="system.volume_up" if go_up else "system.volume_down",
            confidence=0.92,
            corrected_text=command,
            arguments={},
            requires_confirmation=False,
            source="local_rule",
            allow_execution=True,
        )
    return None


def _route_media(text: str, command: str) -> CommandRouteResult | None:
    actions = {
        "play": _contains_any(text, _PLAY),
        "pause": _contains_any(text, _PAUSE),
        "next": _contains_any(text, _NEXT),
        "previous": _contains_any(text, _PREVIOUS),
    }
    matched = [name for name, is_match in actions.items() if is_match]
    if not matched:
        return None
    if len(matched) > 1:
        return CommandRouteResult(
            intent="unknown",
            confidence=0.78,
            corrected_text=command,
            arguments={"candidate_intents": [f"media.{name}" for name in matched]},
            requires_confirmation=True,
            source="unknown",
            allow_execution=False,
        )
    intent = "media.play_pause" if matched[0] in {"play", "pause"} else f"media.{matched[0]}"
    return CommandRouteResult(
        intent=intent,
        confidence=0.94,
        corrected_text=command,
        arguments={},
        requires_confirmation=False,
        source="local_rule",
        allow_execution=True,
    )


def _unknown(command: str) -> CommandRouteResult:
    return CommandRouteResult(
        intent="unknown",
        confidence=0.0,
        corrected_text=command,
        arguments={},
        requires_confirmation=False,
        source="unknown",
        allow_execution=False,
    )


def _normalize(command: str) -> str:
    return _SPACE.sub(" ", command.strip().lower()) if isinstance(command, str) else ""


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms)
