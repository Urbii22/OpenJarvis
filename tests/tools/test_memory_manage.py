from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def memory_file(tmp_path: Path) -> Path:
    p = tmp_path / "MEMORY.md"
    p.write_text("## Knowledge\n\n- User prefers dark mode\n")
    return p


def test_memory_read(memory_file: Path):
    from openjarvis.tools.memory_manage import MemoryManageTool

    tool = MemoryManageTool(memory_path=memory_file)
    result = tool.execute(action="read")
    assert "dark mode" in result.content


def test_memory_add(memory_file: Path):
    from openjarvis.tools.memory_manage import MemoryManageTool

    tool = MemoryManageTool(memory_path=memory_file)
    result = tool.execute(action="add", entry="User works at Acme Corp")
    assert result.success
    assert "Acme Corp" in memory_file.read_text()


def test_memory_remove(memory_file: Path):
    from openjarvis.tools.memory_manage import MemoryManageTool

    tool = MemoryManageTool(memory_path=memory_file)
    tool.execute(action="add", entry="temporary fact")
    result = tool.execute(action="remove", entry="temporary fact")
    assert result.success
    assert "temporary fact" not in memory_file.read_text()


def test_memory_create_if_missing(tmp_path: Path):
    from openjarvis.tools.memory_manage import MemoryManageTool

    path = tmp_path / "MEMORY.md"
    tool = MemoryManageTool(memory_path=path)
    result = tool.execute(action="add", entry="new fact")
    assert result.success
    assert path.exists()
    assert "new fact" in path.read_text()


def test_preference_requires_explicit_or_repeat(memory_file: Path):
    from openjarvis.tools.memory_manage import MemoryManageTool

    tool = MemoryManageTool(memory_path=memory_file)
    rejected = tool.execute(
        action="add_preference",
        key="language",
        value="es",
        explicit=False,
        repeat_count=1,
    )
    assert rejected.success is False

    accepted = tool.execute(
        action="add_preference",
        key="language",
        value="es",
        explicit=True,
    )
    assert accepted.success is True
    read_back = tool.execute(action="get_preference", key="language")
    assert read_back.success is True
    assert read_back.content == "es"


def test_preference_forget(memory_file: Path):
    from openjarvis.tools.memory_manage import MemoryManageTool

    tool = MemoryManageTool(memory_path=memory_file)
    tool.execute(action="add_preference", key="tone", value="concise", explicit=True)
    removed = tool.execute(action="forget_preference", key="tone")
    assert removed.success is True
    missing = tool.execute(action="get_preference", key="tone")
    assert missing.success is False
