from __future__ import annotations

import shutil
from pathlib import Path

import pytest

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
