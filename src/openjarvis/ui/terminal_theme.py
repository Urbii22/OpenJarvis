from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TerminalTheme:
    name: str
    accent: str
    panel: str
    title: str
    state_idle: str
    state_listening: str
    state_thinking: str
    state_speaking: str
    warning: str
    error: str
    muted: str


HACKER_THEME = TerminalTheme(
    name="hacker",
    accent="bold bright_cyan",
    panel="bright_green",
    title="bold bright_green",
    state_idle="bold bright_cyan",
    state_listening="bold bright_green",
    state_thinking="bold yellow",
    state_speaking="bold magenta",
    warning="bold yellow",
    error="bold red",
    muted="dim bright_cyan",
)

PLAIN_THEME = TerminalTheme(
    name="plain",
    accent="",
    panel="",
    title="",
    state_idle="",
    state_listening="",
    state_thinking="",
    state_speaking="",
    warning="",
    error="",
    muted="",
)


def get_terminal_theme(name: str) -> TerminalTheme:
    if name == "plain":
        return PLAIN_THEME
    return HACKER_THEME
