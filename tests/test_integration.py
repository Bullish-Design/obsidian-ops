from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from obsidian_ops.vault import Vault
from obsidian_ops.vault import MAX_READ_SIZE

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_DIR = REPO_ROOT / ".scratch" / "projects" / "15-test-suite-improvements"
SNAPSHOT_DIR = PROJECT_DIR / "integration"
REPORT_PATH = PROJECT_DIR / "INTEGRATION_TEST_REPORT.md"

NOTE_CONTENT = """---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
"""


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class SnapshotRecorder:
    """Capture before/after snapshots for integration tests."""

    def __init__(self, test_name: str, vault_root: Path) -> None:
        self.vault_root = vault_root
        self.case_dir = SNAPSHOT_DIR / test_name
        self.before_dir = self.case_dir / "before"
        self.after_dir = self.case_dir / "after"
        self.result_file = self.case_dir / "result.txt"

        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.before_dir.mkdir(parents=True, exist_ok=True)
        self.after_dir.mkdir(parents=True, exist_ok=True)

    def capture_before(self, *rel_paths: str) -> None:
        self._copy_files(self.before_dir, rel_paths)

    def capture_after(self, *rel_paths: str) -> None:
        self._copy_files(self.after_dir, rel_paths)

    def capture_listing_before(self) -> None:
        listing = "\n".join(
            sorted(path.relative_to(self.vault_root).as_posix() for path in self.vault_root.rglob("*") if path.is_file())
        )
        (self.before_dir / "listing.txt").write_text(f"{listing}\n", encoding="utf-8")

    def write_result(self, value: str) -> None:
        self.result_file.write_text(value, encoding="utf-8")

    def write_error(self, exc: Exception) -> None:
        self.result_file.write_text(f"{exc.__class__.__name__}: {exc}", encoding="utf-8")

    def _copy_files(self, dest_root: Path, rel_paths: tuple[str, ...]) -> None:
        for rel_path in rel_paths:
            src = self.vault_root / rel_path
            dest = dest_root / rel_path
            if src.exists() and src.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)


class ReportWriter:
    """Collect markdown sections and write an integration test report."""

    def __init__(self) -> None:
        self._sections: list[str] = []

    def add_section(self, title: str, content: str) -> None:
        self._sections.append(f"## {title}\n\n{content}\n")

    def write(self) -> Path:
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        body = "# Integration Test Report\n\n"
        if self._sections:
            body += "\n".join(self._sections)
        REPORT_PATH.write_text(body, encoding="utf-8")
        return REPORT_PATH


@pytest.fixture(scope="module")
def integration_vault() -> Path:
    if SNAPSHOT_DIR.exists():
        shutil.rmtree(SNAPSHOT_DIR)

    vault = SNAPSHOT_DIR / "vault"
    vault.mkdir(parents=True, exist_ok=True)

    _write_text(vault / "note.md", NOTE_CONTENT)
    _write_text(vault / "existing.md", "---\ntitle: Existing File\n---\n\nOriginal content that will be overwritten.\n")
    _write_text(vault / "to-delete.md", "# Delete Me\n\nThis file should be deleted.\n")
    _write_text(vault / "Projects/Alpha.md", "---\nstatus: active\nowner: Alice\n---\n\n# Alpha\n\nProject alpha notes.\n")
    _write_text(vault / "Projects/Beta.md", "# Beta\n\nProject beta notes.\n")
    _write_text(vault / ".hidden/secret.md", "# Hidden\n\nThis should be excluded.\n")
    _write_text(vault / "_hidden_dir/internal.md", "# Internal\n\nThis should also be excluded.\n")
    _write_text(vault / "large-file.md", "A" * (MAX_READ_SIZE + 1024))

    return vault


@pytest.fixture(scope="module")
def integration_report() -> ReportWriter:
    return ReportWriter()


@pytest.fixture
def integration_api(integration_vault: Path) -> Vault:
    return Vault(integration_vault)


def _record_report(report: ReportWriter, title: str, method: str, result: str) -> None:
    report.add_section(title, f"**Method**: `{method}`\n**Result**: {result}")


def test_infrastructure_vault_created(integration_vault: Path) -> None:
    assert integration_vault.exists()
    assert (integration_vault / "note.md").exists()
    assert (integration_vault / "Projects/Alpha.md").exists()
    assert (integration_vault / ".hidden/secret.md").exists()
    assert (integration_vault / "_hidden_dir/internal.md").exists()
    assert (integration_vault / "large-file.md").stat().st_size > MAX_READ_SIZE


def test_infrastructure_snapshot_recorder(integration_vault: Path) -> None:
    recorder = SnapshotRecorder("00-infrastructure", integration_vault)
    recorder.capture_before("note.md")
    recorder.write_result("infrastructure-ok")
    recorder.capture_after("note.md")

    assert (SNAPSHOT_DIR / "00-infrastructure" / "before" / "note.md").exists()
    assert (SNAPSHOT_DIR / "00-infrastructure" / "after" / "note.md").exists()
    assert (SNAPSHOT_DIR / "00-infrastructure" / "result.txt").read_text(encoding="utf-8") == "infrastructure-ok"


def test_01_read_file(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    recorder = SnapshotRecorder("01-read-file", integration_vault)
    recorder.capture_before("note.md")
    content = integration_api.read_file("note.md")
    recorder.write_result(content)
    recorder.capture_after("note.md")

    assert content.startswith("---\n")
    assert "title: Meeting Notes" in content
    assert "# Meeting Notes" in content
    assert "## Agenda" in content
    _record_report(integration_report, "01 — Read File", 'vault.read_file("note.md")', "PASS")


def test_02_write_new_file(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    recorder = SnapshotRecorder("02-write-new-file", integration_vault)
    recorder.capture_listing_before()
    new_content = "# New File\n\nCreated by integration test.\n"
    integration_api.write_file("new-file.md", new_content)
    recorder.capture_after("new-file.md")

    assert (integration_vault / "new-file.md").exists()
    assert (integration_vault / "new-file.md").read_text(encoding="utf-8") == new_content
    _record_report(
        integration_report,
        "02 — Write File (New)",
        'vault.write_file("new-file.md", content)',
        "PASS",
    )


def test_03_write_overwrite(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    recorder = SnapshotRecorder("03-write-overwrite", integration_vault)
    recorder.capture_before("existing.md")
    updated = "New content here.\n"
    integration_api.write_file("existing.md", updated)
    recorder.capture_after("existing.md")

    content = (integration_vault / "existing.md").read_text(encoding="utf-8")
    assert "Original content that will be overwritten." not in content
    assert content == updated
    _record_report(
        integration_report,
        "03 — Write File (Overwrite)",
        'vault.write_file("existing.md", "New content here.\\n")',
        "PASS",
    )


def test_04_write_nested_new(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    recorder = SnapshotRecorder("04-write-nested-new", integration_vault)
    recorder.capture_listing_before()
    content = "# Deep Note\n\nNested content.\n"
    integration_api.write_file("Deep/Nested/new.md", content)
    recorder.capture_after("Deep/Nested/new.md")

    path = integration_vault / "Deep" / "Nested" / "new.md"
    assert path.exists()
    assert path.read_text(encoding="utf-8") == content
    _record_report(
        integration_report,
        "04 — Write Nested New",
        'vault.write_file("Deep/Nested/new.md", content)',
        "PASS",
    )


def test_05_delete_file(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    recorder = SnapshotRecorder("05-delete-file", integration_vault)
    recorder.capture_before("to-delete.md")
    integration_api.delete_file("to-delete.md")
    recorder.capture_after("to-delete.md")

    assert not (integration_vault / "to-delete.md").exists()
    with pytest.raises(FileNotFoundError):
        integration_api.read_file("to-delete.md")
    _record_report(integration_report, "05 — Delete File", 'vault.delete_file("to-delete.md")', "PASS")


def test_06_list_files_default(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    recorder = SnapshotRecorder("06-list-files-default", integration_vault)
    files = integration_api.list_files()
    recorder.write_result("\n".join(files))

    assert "note.md" in files
    assert "Projects/Alpha.md" in files
    assert "Projects/Beta.md" in files
    assert ".hidden/secret.md" not in files
    assert "_hidden_dir/internal.md" not in files
    _record_report(integration_report, "06 — List Files (Default)", "vault.list_files()", "PASS")


def test_07_list_files_glob(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    recorder = SnapshotRecorder("07-list-files-glob", integration_vault)
    files = integration_api.list_files("Projects/*.md")
    recorder.write_result("\n".join(files))

    assert files == ["Projects/Alpha.md", "Projects/Beta.md"]
    _record_report(
        integration_report,
        "07 — List Files (Glob)",
        'vault.list_files("Projects/*.md")',
        "PASS",
    )


def test_08_search_files(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    recorder = SnapshotRecorder("08-search-files", integration_vault)
    results = integration_api.search_files("sprint")
    lines = [f"{item.path}: {item.snippet}" for item in results]
    recorder.write_result("\n".join(lines))

    assert any(item.path == "note.md" for item in results)
    note_result = next(item for item in results if item.path == "note.md")
    assert "sprint" in note_result.snippet.lower()
    _record_report(
        integration_report,
        "08 — Search Files",
        'vault.search_files("sprint")',
        "PASS",
    )
