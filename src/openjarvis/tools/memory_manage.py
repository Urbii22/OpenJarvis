"""Manage persistent agent memory (MEMORY.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("memory_manage")
class MemoryManageTool(BaseTool):
    """Manage persistent agent memory (MEMORY.md)."""

    def __init__(self, memory_path: Path | str = "~/.openjarvis/MEMORY.md") -> None:
        self._memory_path = Path(memory_path).expanduser()
        self._legacy_memory_path = Path("MEMORY.md")

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="memory_manage",
            description=(
                "Read, add, update, or remove entries in persistent agent memory."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "read",
                            "add",
                            "update",
                            "remove",
                            "add_preference",
                            "get_preference",
                            "forget_preference",
                        ],
                        "description": "Action to perform on memory.",
                    },
                    "entry": {
                        "type": "string",
                        "description": (
                            "The memory entry content (for add/update/remove)."
                        ),
                    },
                    "new_entry": {
                        "type": "string",
                        "description": (
                            "Replacement content (for update action only)."
                        ),
                    },
                    "key": {
                        "type": "string",
                        "description": "Preference key for preference operations.",
                    },
                    "value": {
                        "type": "string",
                        "description": "Preference value for add_preference.",
                    },
                    "explicit": {
                        "type": "boolean",
                        "description": "Only explicit or repeated preferences are promoted.",
                    },
                    "repeat_count": {
                        "type": "integer",
                        "description": "How many times this preference was observed.",
                    },
                },
                "required": ["action"],
            },
            category="memory",
        )

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action", "read")
        entry = params.get("entry", "")
        new_entry = params.get("new_entry", "")
        if action == "read":
            return self._read()
        elif action == "add":
            return self._add(entry)
        elif action == "update":
            return self._update(entry, new_entry)
        elif action == "remove":
            return self._remove(entry)
        elif action == "add_preference":
            return self._add_preference(
                key=params.get("key", ""),
                value=params.get("value", ""),
                explicit=bool(params.get("explicit", False)),
                repeat_count=int(params.get("repeat_count", 1)),
            )
        elif action == "get_preference":
            return self._get_preference(params.get("key", ""))
        elif action == "forget_preference":
            return self._forget_preference(params.get("key", ""))
        return ToolResult(
            tool_name=self.spec.name,
            success=False,
            content=f"Unknown action: {action}",
        )

    def _resolve_memory_path(self) -> Path:
        if self._memory_path.exists() or not self._legacy_memory_path.exists():
            return self._memory_path
        return self._legacy_memory_path

    def _read(self) -> ToolResult:
        content = ""
        path = self._resolve_memory_path()
        if path.exists():
            content = path.read_text()
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=content or "(empty)",
        )

    def _add(self, entry: str) -> ToolResult:
        if not entry:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Entry cannot be empty.",
            )
        path = self._resolve_memory_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text() if path.exists() else ""
        path.write_text(existing.rstrip() + f"\n- {entry}\n")
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Added: {entry}",
        )

    def _update(self, old: str, new: str) -> ToolResult:
        path = self._resolve_memory_path()
        if not path.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Memory file does not exist.",
            )
        text = path.read_text()
        if old not in text:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Entry not found: {old}",
            )
        path.write_text(text.replace(old, new, 1))
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Updated: {old} -> {new}",
        )

    def _remove(self, entry: str) -> ToolResult:
        path = self._resolve_memory_path()
        if not path.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Memory file does not exist.",
            )
        text = path.read_text()
        lines = text.split("\n")
        new_lines = [ln for ln in lines if entry not in ln]
        if len(new_lines) == len(lines):
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Entry not found: {entry}",
            )
        path.write_text("\n".join(new_lines))
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Removed: {entry}",
        )

    def _add_preference(
        self,
        *,
        key: str,
        value: str,
        explicit: bool,
        repeat_count: int,
    ) -> ToolResult:
        if not key or not value:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Preference key and value are required.",
            )
        if self._looks_sensitive(value):
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Preference looks sensitive and was not stored.",
            )
        if not explicit and repeat_count < 2:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Preference ignored: needs explicit consent or repetition.",
            )
        prefs = self._parse_preferences()
        prefs[key.strip()] = value.strip()
        self._write_preferences(prefs)
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Stored preference: {key.strip()}",
        )

    def _get_preference(self, key: str) -> ToolResult:
        if not key:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Preference key is required.",
            )
        prefs = self._parse_preferences()
        if key not in prefs:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Preference not found: {key}",
            )
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=prefs[key],
        )

    def _forget_preference(self, key: str) -> ToolResult:
        if not key:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Preference key is required.",
            )
        prefs = self._parse_preferences()
        if key not in prefs:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Preference not found: {key}",
            )
        del prefs[key]
        self._write_preferences(prefs)
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Forgot preference: {key}",
        )

    def _parse_preferences(self) -> dict[str, str]:
        path = self._resolve_memory_path()
        if not path.exists():
            return {}
        text = path.read_text()
        prefs: dict[str, str] = {}
        in_section = False
        for raw in text.splitlines():
            line = raw.strip()
            if line.lower() == "## preferences":
                in_section = True
                continue
            if in_section and line.startswith("## "):
                break
            if not in_section or not line.startswith("- "):
                continue
            pair = line[2:].split(":", 1)
            if len(pair) != 2:
                continue
            prefs[pair[0].strip()] = pair[1].strip()
        return prefs

    def _write_preferences(self, prefs: dict[str, str]) -> None:
        path = self._resolve_memory_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text() if path.exists() else ""
        lines = existing.splitlines()
        out: list[str] = []
        in_section = False
        section_written = False
        for line in lines:
            stripped = line.strip()
            if stripped.lower() == "## preferences":
                in_section = True
                if not section_written:
                    out.append("## Preferences")
                    for k, v in sorted(prefs.items()):
                        out.append(f"- {k}: {v}")
                    section_written = True
                continue
            if in_section and stripped.startswith("## "):
                in_section = False
                out.append(line)
                continue
            if not in_section:
                out.append(line)
        if not section_written:
            if out and out[-1].strip():
                out.append("")
            out.append("## Preferences")
            for k, v in sorted(prefs.items()):
                out.append(f"- {k}: {v}")
        path.write_text("\n".join(out).rstrip() + "\n")

    def _looks_sensitive(self, text: str) -> bool:
        lower = text.lower()
        needles = ("password", "token", "api key", "secret", "ssn")
        return any(n in lower for n in needles)
