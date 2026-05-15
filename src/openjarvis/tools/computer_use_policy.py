from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "known_hosts",
    "credentials",
    "credentials.json",
    "keychain",
    "login.keychain-db",
}

SENSITIVE_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".kdbx",
}

HIGH_RISK_TOOLS = {"delete_path", "shell_exec"}
MEDIUM_RISK_TOOLS = {
    "create_folder",
    "file_write",
    "copy_path",
    "move_path",
}
LOW_RISK_TOOLS = {
    "open_application",
    "open_path",
    "list_directory",
    "find_files",
    "file_read",
}


@dataclass(frozen=True)
class ActionRisk:
    level: str
    requires_confirmation: bool
    blocked: bool = False
    reason: str = ""


def normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def is_blocked_path(path: str | Path) -> bool:
    resolved = normalize_path(path)
    lowered_parts = {part.lower() for part in resolved.parts}
    name = resolved.name.lower()
    suffix = resolved.suffix.lower()

    if name in SENSITIVE_NAMES:
        return True
    if suffix in SENSITIVE_SUFFIXES:
        return True
    if ".ssh" in lowered_parts:
        return True
    if "credentials" in lowered_parts and resolved.is_file():
        return True
    return False


def _extract_paths(params: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for key in ("path", "source", "destination"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(normalize_path(value))
    return paths


def classify_computer_action(tool_name: str, params: dict[str, Any]) -> ActionRisk:
    for path in _extract_paths(params):
        if is_blocked_path(path):
            return ActionRisk(
                level="blocked",
                requires_confirmation=False,
                blocked=True,
                reason=f"Blocked sensitive path: {path}",
            )

    if tool_name in HIGH_RISK_TOOLS:
        return ActionRisk(level="high", requires_confirmation=True)
    if tool_name in MEDIUM_RISK_TOOLS:
        return ActionRisk(level="medium", requires_confirmation=True)
    if tool_name in LOW_RISK_TOOLS:
        return ActionRisk(level="low", requires_confirmation=False)
    return ActionRisk(level="medium", requires_confirmation=True)
