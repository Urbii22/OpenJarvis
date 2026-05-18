"""High-level desktop computer-use tools (apps, files, folders)."""

from __future__ import annotations

import fnmatch
import os
import shlex
import shutil
import subprocess
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, List

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.security.file_policy import is_sensitive_file
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.tools.computer_use_policy import classify_computer_action


def _safe_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _policy_block(tool_name: str, params: dict[str, Any]) -> ToolResult | None:
    risk = classify_computer_action(tool_name, params)
    if risk.blocked:
        return ToolResult(tool_name=tool_name, content=risk.reason, success=False)
    return None


def _split_args(args: str) -> list[str]:
    if not args:
        return []
    return shlex.split(args, posix=False)


def _normalize_name(value: str) -> str:
    chars = []
    for char in value.lower():
        chars.append(char if char.isalnum() else " ")
    return " ".join("".join(chars).split())


def _iter_search_roots(raw_path: str | None) -> list[Path]:
    if raw_path and raw_path.strip():
        return [_safe_path(raw_path)]
    if os.name == "nt":
        roots: list[Path] = []
        for code in range(ord("A"), ord("Z") + 1):
            drive = Path(f"{chr(code)}:\\")
            if drive.exists():
                roots.append(drive)
        return roots or [Path(os.environ.get("SystemDrive", "C:") + "\\")]
    return [Path("/")]


def _score_name_match(name: str, query: str) -> float:
    normalized_name = _normalize_name(name)
    normalized_query = _normalize_name(query)
    if not normalized_query:
        return 0.0
    if normalized_name == normalized_query:
        return 1.0
    if normalized_query in normalized_name:
        return 0.95
    name_tokens = normalized_name.split()
    query_tokens = normalized_query.split()
    if query_tokens and all(token in normalized_name for token in query_tokens):
        return 0.9
    ratio = SequenceMatcher(None, normalized_query, normalized_name).ratio()
    token_ratio = 0.0
    if name_tokens and query_tokens:
        token_ratio = max(
            SequenceMatcher(None, token, candidate).ratio()
            for token in query_tokens
            for candidate in name_tokens
        )
    return max(ratio, token_ratio * 0.85)


@ToolRegistry.register("open_application")
class OpenApplicationTool(BaseTool):
    tool_id = "open_application"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="open_application",
            description="Open a desktop application by name or executable path.",
            parameters={
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "App name or executable path."},
                    "args": {"type": "string", "description": "Optional command arguments."},
                },
                "required": ["app"],
            },
            category="system",
            required_capabilities=["code:execute"],
        )

    def execute(self, **params: Any) -> ToolResult:
        app = (params.get("app") or "").strip()
        args = (params.get("args") or "").strip()
        if not app:
            return ToolResult(tool_name="open_application", content="Missing app.", success=False)
        blocked = _policy_block(self.tool_id, params)
        if blocked is not None:
            return blocked
        try:
            if os.name == "nt":
                expanded_app = Path(app).expanduser()
                split_args = _split_args(args)
                if expanded_app.exists():
                    subprocess.Popen([str(expanded_app), *split_args])
                else:
                    command = [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "Start-Process",
                        "-FilePath",
                        app,
                    ]
                    if split_args:
                        command.extend(["-ArgumentList", " ".join(split_args)])
                    subprocess.Popen(command)
            else:
                subprocess.Popen([app, *_split_args(args)])
            return ToolResult(tool_name="open_application", content=f"Opened: {app}", success=True)
        except Exception as exc:
            return ToolResult(tool_name="open_application", content=f"Open failed: {exc}", success=False)


@ToolRegistry.register("open_path")
class OpenPathTool(BaseTool):
    tool_id = "open_path"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="open_path",
            description="Open a file or folder in the system UI (Explorer/Finder).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File or folder path."},
                },
                "required": ["path"],
            },
            category="filesystem",
            required_capabilities=["code:execute"],
        )

    def execute(self, **params: Any) -> ToolResult:
        raw = (params.get("path") or "").strip()
        if not raw:
            return ToolResult(tool_name="open_path", content="Missing path.", success=False)
        blocked = _policy_block(self.tool_id, params)
        if blocked is not None:
            return blocked
        try:
            path = _safe_path(raw)
            if not path.exists():
                return ToolResult(tool_name="open_path", content=f"Path not found: {path}", success=False)
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return ToolResult(tool_name="open_path", content=f"Opened: {path}", success=True)
        except Exception as exc:
            return ToolResult(tool_name="open_path", content=f"Open failed: {exc}", success=False)


@ToolRegistry.register("list_directory")
class ListDirectoryTool(BaseTool):
    tool_id = "list_directory"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="list_directory",
            description="List files and folders in a directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path."},
                    "recursive": {"type": "boolean", "description": "List recursively (default false)."},
                    "max_entries": {"type": "integer", "description": "Max entries to return (default 200)."},
                },
                "required": ["path"],
            },
            category="filesystem",
        )

    def execute(self, **params: Any) -> ToolResult:
        raw = (params.get("path") or "").strip()
        recursive = bool(params.get("recursive", False))
        max_entries = int(params.get("max_entries", 200) or 200)
        max_entries = min(max(max_entries, 1), 2000)
        if not raw:
            return ToolResult(tool_name="list_directory", content="Missing path.", success=False)
        blocked = _policy_block(self.tool_id, params)
        if blocked is not None:
            return blocked
        try:
            base = _safe_path(raw)
            if not base.exists() or not base.is_dir():
                return ToolResult(tool_name="list_directory", content=f"Not a directory: {base}", success=False)
            items: List[str] = []
            it = base.rglob("*") if recursive else base.iterdir()
            for entry in it:
                rel = entry.relative_to(base)
                kind = "dir" if entry.is_dir() else "file"
                items.append(f"{kind}\t{rel}")
                if len(items) >= max_entries:
                    items.append("... (truncated)")
                    break
            return ToolResult(tool_name="list_directory", content="\n".join(items) if items else "(empty)", success=True)
        except Exception as exc:
            return ToolResult(tool_name="list_directory", content=f"List failed: {exc}", success=False)


@ToolRegistry.register("find_files")
class FindFilesTool(BaseTool):
    tool_id = "find_files"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="find_files",
            description="Find files by glob pattern in a directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional search root directory. If omitted, search the whole system."},
                    "pattern": {"type": "string", "description": "Optional glob pattern (e.g. *.txt)."},
                    "query": {"type": "string", "description": "Optional fuzzy filename query, such as report or project plan."},
                    "recursive": {"type": "boolean", "description": "Recursive search (default true)."},
                    "max_results": {"type": "integer", "description": "Max results (default 200)."},
                },
                "required": [],
            },
            category="filesystem",
        )

    def execute(self, **params: Any) -> ToolResult:
        raw = (params.get("path") or "").strip()
        pattern = (params.get("pattern") or "").strip()
        query = (params.get("query") or "").strip()
        recursive = bool(params.get("recursive", True))
        max_results = int(params.get("max_results", 200) or 200)
        max_results = min(max(max_results, 1), 500)
        if not pattern and not query:
            return ToolResult(tool_name="find_files", content="Missing pattern or query.", success=False)
        blocked = _policy_block(self.tool_id, params)
        if blocked is not None:
            return blocked
        try:
            roots = _iter_search_roots(raw)
            candidates: list[tuple[float, str]] = []
            for base in roots:
                if not base.exists() or not base.is_dir():
                    continue
                iterator = base.rglob("*") if recursive else base.iterdir()
                try:
                    for entry in iterator:
                        try:
                            if not entry.is_file():
                                continue
                        except OSError:
                            continue
                        matched = False
                        score = 0.0
                        if pattern and fnmatch.fnmatch(entry.name, pattern):
                            matched = True
                            score = max(score, 0.8)
                        if query:
                            query_score = _score_name_match(entry.name, query)
                            if query_score >= 0.55:
                                matched = True
                                score = max(score, query_score)
                        if matched:
                            candidates.append((score, str(entry)))
                except (OSError, PermissionError):
                    continue

            if not candidates:
                return ToolResult(tool_name="find_files", content="(no matches)", success=True)

            candidates.sort(key=lambda item: (-item[0], item[1].lower()))
            lines = [path for _, path in candidates[:max_results]]
            if len(candidates) > max_results:
                lines.append("... (truncated)")
            return ToolResult(tool_name="find_files", content="\n".join(lines), success=True)
        except Exception as exc:
            return ToolResult(tool_name="find_files", content=f"Find failed: {exc}", success=False)


@ToolRegistry.register("create_folder")
class CreateFolderTool(BaseTool):
    tool_id = "create_folder"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="create_folder",
            description="Create a folder (and optionally parent folders).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Folder path to create."},
                    "parents": {"type": "boolean", "description": "Create parents (default true)."},
                },
                "required": ["path"],
            },
            category="filesystem",
            required_capabilities=["file:write"],
        )

    def execute(self, **params: Any) -> ToolResult:
        raw = (params.get("path") or "").strip()
        parents = bool(params.get("parents", True))
        if not raw:
            return ToolResult(tool_name="create_folder", content="Missing path.", success=False)
        blocked = _policy_block(self.tool_id, params)
        if blocked is not None:
            return blocked
        try:
            path = _safe_path(raw)
            if is_sensitive_file(path):
                return ToolResult(tool_name="create_folder", content=f"Access denied: {path}", success=False)
            path.mkdir(parents=parents, exist_ok=True)
            return ToolResult(tool_name="create_folder", content=f"Created: {path}", success=True)
        except Exception as exc:
            return ToolResult(tool_name="create_folder", content=f"Create failed: {exc}", success=False)


@ToolRegistry.register("copy_path")
class CopyPathTool(BaseTool):
    tool_id = "copy_path"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="copy_path",
            description="Copy file or directory to another path.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source path."},
                    "destination": {"type": "string", "description": "Destination path."},
                    "overwrite": {"type": "boolean", "description": "Overwrite destination if exists."},
                },
                "required": ["source", "destination"],
            },
            category="filesystem",
            requires_confirmation=True,
            required_capabilities=["file:write"],
        )

    def execute(self, **params: Any) -> ToolResult:
        src_raw = (params.get("source") or "").strip()
        dst_raw = (params.get("destination") or "").strip()
        overwrite = bool(params.get("overwrite", False))
        if not src_raw or not dst_raw:
            return ToolResult(tool_name="copy_path", content="Missing source or destination.", success=False)
        blocked = _policy_block(self.tool_id, params)
        if blocked is not None:
            return blocked
        try:
            src = _safe_path(src_raw)
            dst = _safe_path(dst_raw)
            if not src.exists():
                return ToolResult(tool_name="copy_path", content=f"Source not found: {src}", success=False)
            if is_sensitive_file(src) or is_sensitive_file(dst):
                return ToolResult(tool_name="copy_path", content="Access denied for sensitive path.", success=False)
            if dst.exists() and not overwrite:
                return ToolResult(tool_name="copy_path", content=f"Destination exists: {dst}", success=False)
            if src.is_dir():
                if dst.exists() and overwrite:
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            return ToolResult(tool_name="copy_path", content=f"Copied to: {dst}", success=True)
        except Exception as exc:
            return ToolResult(tool_name="copy_path", content=f"Copy failed: {exc}", success=False)


@ToolRegistry.register("move_path")
class MovePathTool(BaseTool):
    tool_id = "move_path"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="move_path",
            description="Move or rename file/directory.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source path."},
                    "destination": {"type": "string", "description": "Destination path."},
                    "overwrite": {"type": "boolean", "description": "Overwrite destination if exists."},
                },
                "required": ["source", "destination"],
            },
            category="filesystem",
            requires_confirmation=True,
            required_capabilities=["file:write"],
        )

    def execute(self, **params: Any) -> ToolResult:
        src_raw = (params.get("source") or "").strip()
        dst_raw = (params.get("destination") or "").strip()
        overwrite = bool(params.get("overwrite", False))
        if not src_raw or not dst_raw:
            return ToolResult(tool_name="move_path", content="Missing source or destination.", success=False)
        blocked = _policy_block(self.tool_id, params)
        if blocked is not None:
            return blocked
        try:
            src = _safe_path(src_raw)
            dst = _safe_path(dst_raw)
            if not src.exists():
                return ToolResult(tool_name="move_path", content=f"Source not found: {src}", success=False)
            if is_sensitive_file(src) or is_sensitive_file(dst):
                return ToolResult(tool_name="move_path", content="Access denied for sensitive path.", success=False)
            if dst.exists():
                if not overwrite:
                    return ToolResult(tool_name="move_path", content=f"Destination exists: {dst}", success=False)
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return ToolResult(tool_name="move_path", content=f"Moved to: {dst}", success=True)
        except Exception as exc:
            return ToolResult(tool_name="move_path", content=f"Move failed: {exc}", success=False)


@ToolRegistry.register("delete_path")
class DeletePathTool(BaseTool):
    tool_id = "delete_path"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="delete_path",
            description="Delete file or directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to delete."},
                    "recursive": {"type": "boolean", "description": "Delete directories recursively (default false)."},
                    "missing_ok": {"type": "boolean", "description": "Do not fail if path is missing (default true)."},
                },
                "required": ["path"],
            },
            category="filesystem",
            requires_confirmation=True,
            required_capabilities=["file:write"],
            risk_level="high",
        )

    def execute(self, **params: Any) -> ToolResult:
        raw = (params.get("path") or "").strip()
        recursive = bool(params.get("recursive", False))
        missing_ok = bool(params.get("missing_ok", True))
        if not raw:
            return ToolResult(tool_name="delete_path", content="Missing path.", success=False)
        blocked = _policy_block(self.tool_id, params)
        if blocked is not None:
            return blocked
        try:
            path = _safe_path(raw)
            if is_sensitive_file(path):
                return ToolResult(tool_name="delete_path", content=f"Access denied: {path}", success=False)
            if not path.exists():
                if missing_ok:
                    return ToolResult(tool_name="delete_path", content=f"Path already missing: {path}", success=True)
                return ToolResult(tool_name="delete_path", content=f"Path not found: {path}", success=False)
            if path.is_dir():
                if not recursive:
                    return ToolResult(tool_name="delete_path", content="Directory delete requires recursive=true.", success=False)
                shutil.rmtree(path)
            else:
                path.unlink()
            return ToolResult(tool_name="delete_path", content=f"Deleted: {path}", success=True)
        except Exception as exc:
            return ToolResult(tool_name="delete_path", content=f"Delete failed: {exc}", success=False)


__all__ = [
    "OpenApplicationTool",
    "OpenPathTool",
    "ListDirectoryTool",
    "FindFilesTool",
    "CreateFolderTool",
    "CopyPathTool",
    "MovePathTool",
    "DeletePathTool",
]
