from pathlib import Path

from openjarvis.tools.computer_use import (
    CreateFolderTool,
    FindFilesTool,
    ListDirectoryTool,
)
from openjarvis.tools.computer_use_policy import (
    classify_computer_action,
    is_blocked_path,
)


def test_blocks_sensitive_env_file(tmp_path: Path):
    secret = tmp_path / ".env"
    secret.write_text("TOKEN=abc", encoding="utf-8")

    assert is_blocked_path(secret) is True


def test_list_directory_is_low_risk(tmp_path: Path):
    risk = classify_computer_action("list_directory", {"path": str(tmp_path)})

    assert risk.level == "low"
    assert risk.requires_confirmation is False
    assert risk.blocked is False


def test_open_application_is_low_risk():
    risk = classify_computer_action("open_application", {"app": "Spotify"})

    assert risk.level == "low"
    assert risk.requires_confirmation is False
    assert risk.blocked is False


def test_delete_path_is_high_risk(tmp_path: Path):
    target = tmp_path / "folder"
    target.mkdir()

    risk = classify_computer_action(
        "delete_path",
        {"path": str(target), "recursive": True},
    )

    assert risk.level == "high"
    assert risk.requires_confirmation is True
    assert risk.blocked is False


def test_sensitive_file_read_is_blocked(tmp_path: Path):
    secret = tmp_path / "id_rsa"
    secret.write_text("private", encoding="utf-8")

    risk = classify_computer_action("file_read", {"path": str(secret)})

    assert risk.blocked is True
    assert "sensitive" in risk.reason.lower()


def test_create_folder_blocks_sensitive_target(tmp_path: Path):
    tool = CreateFolderTool()

    result = tool.execute(path=str(tmp_path / ".ssh" / "new"))

    assert result.success is False
    assert "blocked" in result.content.lower() or "denied" in result.content.lower()


def test_list_directory_returns_relative_entries(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.txt").write_text("hello", encoding="utf-8")

    result = ListDirectoryTool().execute(path=str(tmp_path), recursive=True)

    assert result.success is True
    assert "dir\tnotes" in result.content
    assert (
        "file\tnotes\\a.txt" in result.content
        or "file\tnotes/a.txt" in result.content
    )


def test_find_files_supports_fuzzy_name_matching(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "Project Plan Final.md"
    target.write_text("draft", encoding="utf-8")

    result = FindFilesTool().execute(path=str(tmp_path), query="proj plan")

    assert result.success is True
    assert "Project Plan Final.md" in result.content


def test_find_files_supports_pattern_matching_without_exact_name(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    target = src / "budget_report_2026.txt"
    target.write_text("ok", encoding="utf-8")

    result = FindFilesTool().execute(path=str(tmp_path), pattern="*report*")

    assert result.success is True
    assert "budget_report_2026.txt" in result.content
