from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from obsidian_ops.errors import ContentPatchError, FileTooLargeError, FrontmatterError, PathError
from obsidian_ops.frontmatter import parse_frontmatter
from obsidian_ops.vault import MAX_READ_SIZE, Vault

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
            sorted(
                path.relative_to(self.vault_root).as_posix() for path in self.vault_root.rglob("*") if path.is_file()
            )
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
        self._entries: list[dict[str, str]] = []

    def add_entry(self, title: str, method: str, result: str) -> None:
        self._entries.append({"title": title, "method": method, "result": result})

    def _case_dir_for_title(self, title: str) -> Path | None:
        prefix = title.split(" ", 1)[0]
        matches = sorted(SNAPSHOT_DIR.glob(f"{prefix}-*"))
        if matches:
            return matches[0]
        return None

    def _read_snapshot_files(self, root: Path) -> list[tuple[str, str]]:
        if not root.exists():
            return []
        files: list[tuple[str, str]] = []
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = path.relative_to(root).as_posix()
            files.append((rel, path.read_text(encoding="utf-8")))
        return files

    def _code_lang_for_path(self, rel_path: str) -> str:
        if rel_path.endswith(".md"):
            return "markdown"
        return "text"

    def write(self) -> Path:
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        lines: list[str] = ["# Integration Test Report", ""]

        for entry in self._entries:
            title = entry["title"]
            method = entry["method"]
            result = entry["result"]
            lines.append(f"## {title}")
            lines.append("")
            lines.append(f"**Method**: `{method}`")
            lines.append(f"**Result**: {result}")
            lines.append("")

            case_dir = self._case_dir_for_title(title)
            if case_dir is None:
                continue

            before_files = self._read_snapshot_files(case_dir / "before")
            for rel_path, content in before_files:
                lines.append(f"### Before (`{rel_path}`)")
                lines.append(f"```{self._code_lang_for_path(rel_path)}")
                lines.append(content.rstrip("\n"))
                lines.append("```")
                lines.append("")

            after_files = self._read_snapshot_files(case_dir / "after")
            for rel_path, content in after_files:
                lines.append(f"### After (`{rel_path}`)")
                lines.append(f"```{self._code_lang_for_path(rel_path)}")
                lines.append(content.rstrip("\n"))
                lines.append("```")
                lines.append("")

            result_path = case_dir / "result.txt"
            if result_path.exists():
                heading = "### Exception" if "raised" in result.lower() else "### Returned Value"
                lines.append(heading)
                lines.append("```text")
                lines.append(result_path.read_text(encoding="utf-8").rstrip("\n"))
                lines.append("```")
                lines.append("")

        REPORT_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
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
    _write_text(
        vault / "Projects/Alpha.md", "---\nstatus: active\nowner: Alice\n---\n\n# Alpha\n\nProject alpha notes.\n"
    )
    _write_text(vault / "Projects/Beta.md", "# Beta\n\nProject beta notes.\n")
    _write_text(vault / ".hidden/secret.md", "# Hidden\n\nThis should be excluded.\n")
    _write_text(vault / "_hidden_dir/internal.md", "# Internal\n\nThis should also be excluded.\n")
    _write_text(vault / "large-file.md", "A" * (MAX_READ_SIZE + 1024))

    return vault


@pytest.fixture(scope="module")
def integration_report() -> ReportWriter:
    return ReportWriter()


@pytest.fixture(scope="module", autouse=True)
def write_integration_report(integration_report: ReportWriter) -> None:
    yield
    integration_report.write()


@pytest.fixture
def integration_api(integration_vault: Path) -> Vault:
    return Vault(integration_vault)


def _record_report(report: ReportWriter, title: str, method: str, result: str) -> None:
    report.add_entry(title, method, result)


def _seed_file(vault_root: Path, rel_path: str, content: str) -> Path:
    path = vault_root / rel_path
    _write_text(path, content)
    return path


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


def test_06_list_files_default(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    recorder = SnapshotRecorder("06-list-files-default", integration_vault)
    files = integration_api.list_files()
    recorder.write_result("\n".join(files))

    assert "note.md" in files
    assert "Projects/Alpha.md" in files
    assert "Projects/Beta.md" in files
    assert ".hidden/secret.md" not in files
    assert "_hidden_dir/internal.md" not in files
    _record_report(integration_report, "06 — List Files (Default)", "vault.list_files()", "PASS")


def test_vcs_undo_last_change_restores_original_content(tmp_path: Path) -> None:
    if shutil.which("jj") is None:
        pytest.skip("jj not installed")

    vault_root = tmp_path / "jj-vault"
    vault_root.mkdir()

    def run_jj(*args: str) -> None:
        result = subprocess.run(
            ["jj", *args],
            cwd=vault_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            pytest.fail(f"jj {' '.join(args)} failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")

    run_jj("git", "init")

    note = vault_root / "note.md"
    note.write_text("original\n", encoding="utf-8")

    vault = Vault(vault_root)
    vault.commit("seed")

    note.write_text("modified\n", encoding="utf-8")
    vault.commit("mutate")

    result = vault.undo_last_change()

    assert result.restored is True
    assert result.warning is None
    assert note.read_text(encoding="utf-8") == "original\n"


def test_vcs_sync_round_trip_with_local_remote(tmp_path: Path) -> None:
    if shutil.which("jj") is None:
        pytest.skip("jj not installed")

    remote_bare = tmp_path / "remote.git"
    vault_root = tmp_path / "vault"
    remote_bare.mkdir(parents=True)
    vault_root.mkdir(parents=True)

    def run_cmd(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            list(args),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            pytest.fail(f"command failed: {' '.join(args)}\nstdout: {result.stdout}\nstderr: {result.stderr}")
        return result

    run_cmd(remote_bare, "git", "init", "--bare")

    vault = Vault(vault_root)
    ready = vault.ensure_sync_ready()
    assert ready.status.value == "ready"
    run_cmd(vault_root, "jj", "config", "set", "--repo", "user.name", "Integration Test")
    run_cmd(vault_root, "jj", "config", "set", "--repo", "user.email", "integration@example.com")

    vault.configure_sync_remote(remote_bare.as_uri(), token=None)

    note = vault_root / "note.md"
    note.write_text("hello sync\n", encoding="utf-8")
    vault.commit("seed sync")

    sync_result = vault.sync()
    assert sync_result.ok is True

    refs = run_cmd(tmp_path, "git", "--git-dir", remote_bare.as_posix(), "rev-list", "--count", "--all")
    assert int(refs.stdout.strip()) >= 1


def test_vcs_sync_conflict_records_conflict_state(tmp_path: Path) -> None:
    if shutil.which("jj") is None:
        pytest.skip("jj not installed")

    remote_bare = tmp_path / "remote.git"
    vault_root = tmp_path / "vault"
    remote_bare.mkdir(parents=True)
    vault_root.mkdir(parents=True)

    def run_cmd(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            list(args),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            pytest.fail(f"command failed: {' '.join(args)}\nstdout: {result.stdout}\nstderr: {result.stderr}")
        return result

    run_cmd(remote_bare, "git", "init", "--bare")

    vault = Vault(vault_root)
    assert vault.ensure_sync_ready().status.value == "ready"
    run_cmd(vault_root, "jj", "config", "set", "--repo", "user.name", "Integration Test")
    run_cmd(vault_root, "jj", "config", "set", "--repo", "user.email", "integration@example.com")
    vault.configure_sync_remote(remote_bare.as_uri(), token=None)

    note = vault_root / "note.md"
    note.write_text("base\n", encoding="utf-8")
    vault.commit("base")
    assert vault.sync().ok is True

    note.write_text("local change\n", encoding="utf-8")
    vault.commit("local change")

    clone_dir = tmp_path / "clone"
    run_cmd(tmp_path, "git", "clone", remote_bare.as_posix(), clone_dir.as_posix())
    run_cmd(clone_dir, "git", "config", "user.email", "integration@example.com")
    run_cmd(clone_dir, "git", "config", "user.name", "Integration Test")
    (clone_dir / "note.md").write_text("remote change\n", encoding="utf-8")
    run_cmd(clone_dir, "git", "add", "note.md")
    run_cmd(clone_dir, "git", "commit", "-m", "remote change")
    run_cmd(clone_dir, "git", "push", "origin", "HEAD:main")

    result = vault.sync()
    state = vault.sync_status()
    assert state["last_sync_ok"] is result.ok
    if result.conflict:
        assert state["conflict_active"] is True
        assert state["conflict_bookmark"] is not None


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


def test_09_get_frontmatter(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    _seed_file(integration_vault, "fm-get.md", NOTE_CONTENT)
    recorder = SnapshotRecorder("09-get-frontmatter", integration_vault)
    recorder.capture_before("fm-get.md")

    fm = integration_api.get_frontmatter("fm-get.md")
    recorder.write_result(str(fm))
    recorder.capture_after("fm-get.md")

    assert fm is not None
    assert fm["title"] == "Meeting Notes"
    assert fm["tags"] == ["work", "weekly"]
    assert fm["status"] == "draft"
    assert fm["priority"] == "high"
    assert fm["metadata"] == {"author": "Jane", "reviewed": False}
    _record_report(
        integration_report,
        "09 — Get Frontmatter",
        'vault.get_frontmatter("fm-get.md")',
        "PASS",
    )


def test_10_set_frontmatter(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    path = _seed_file(integration_vault, "fm-set.md", NOTE_CONTENT)
    before_text = path.read_text(encoding="utf-8")
    _before_data, before_body = parse_frontmatter(before_text)
    recorder = SnapshotRecorder("10-set-frontmatter", integration_vault)
    recorder.capture_before("fm-set.md")

    integration_api.set_frontmatter("fm-set.md", {"title": "Replaced", "new_field": True})
    recorder.capture_after("fm-set.md")

    after_text = path.read_text(encoding="utf-8")
    data, body = parse_frontmatter(after_text)
    assert data == {"title": "Replaced", "new_field": True}
    assert body == before_body
    assert "tags" not in data
    assert "status" not in data
    assert "priority" not in data
    _record_report(
        integration_report,
        "10 — Set Frontmatter",
        'vault.set_frontmatter("fm-set.md", {"title": "Replaced", "new_field": true})',
        "PASS",
    )


def test_11_update_frontmatter_merge(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    _seed_file(integration_vault, "fm-merge.md", NOTE_CONTENT)
    recorder = SnapshotRecorder("11-update-frontmatter-merge", integration_vault)
    recorder.capture_before("fm-merge.md")

    integration_api.update_frontmatter("fm-merge.md", {"status": "published", "reviewer": "Bob"})
    recorder.capture_after("fm-merge.md")

    fm = integration_api.get_frontmatter("fm-merge.md")
    assert fm is not None
    assert fm["title"] == "Meeting Notes"
    assert fm["tags"] == ["work", "weekly"]
    assert fm["priority"] == "high"
    assert fm["status"] == "published"
    assert fm["reviewer"] == "Bob"
    _record_report(
        integration_report,
        "11 — Update Frontmatter (Merge)",
        'vault.update_frontmatter("fm-merge.md", {"status": "published", "reviewer": "Bob"})',
        "PASS",
    )


def test_12_update_frontmatter_nested_merge(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    _seed_file(integration_vault, "fm-shallow.md", NOTE_CONTENT)
    recorder = SnapshotRecorder("12-update-frontmatter-nested-merge", integration_vault)
    recorder.capture_before("fm-shallow.md")

    integration_api.update_frontmatter("fm-shallow.md", {"metadata": {"author": "New"}})
    recorder.capture_after("fm-shallow.md")

    fm = integration_api.get_frontmatter("fm-shallow.md")
    assert fm is not None
    assert fm["metadata"] == {"author": "New", "reviewed": False}
    _record_report(
        integration_report,
        "12 — Update Frontmatter (Nested Merge)",
        'vault.update_frontmatter("fm-shallow.md", {"metadata": {"author": "New"}})',
        "PASS",
    )


def test_13_update_frontmatter_creates(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    path = _seed_file(integration_vault, "no-fm.md", "# No Frontmatter\n\nBody stays here.\n")
    before_text = path.read_text(encoding="utf-8")
    recorder = SnapshotRecorder("13-update-frontmatter-creates", integration_vault)
    recorder.capture_before("no-fm.md")

    integration_api.update_frontmatter("no-fm.md", {"title": "Added"})
    recorder.capture_after("no-fm.md")

    after_text = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(after_text)
    assert fm == {"title": "Added"}
    assert body == before_text
    _record_report(
        integration_report,
        "13 — Update Frontmatter (Creates)",
        'vault.update_frontmatter("no-fm.md", {"title": "Added"})',
        "PASS",
    )


def test_14_delete_frontmatter_field(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    _seed_file(integration_vault, "fm-delete.md", NOTE_CONTENT)
    recorder = SnapshotRecorder("14-delete-frontmatter-field", integration_vault)
    recorder.capture_before("fm-delete.md")

    integration_api.delete_frontmatter_field("fm-delete.md", "priority")
    recorder.capture_after("fm-delete.md")

    fm = integration_api.get_frontmatter("fm-delete.md")
    assert fm is not None
    assert "priority" not in fm
    assert fm["title"] == "Meeting Notes"
    assert fm["status"] == "draft"
    _record_report(
        integration_report,
        "14 — Delete Frontmatter Field",
        'vault.delete_frontmatter_field("fm-delete.md", "priority")',
        "PASS",
    )


def test_15_delete_frontmatter_field_noop(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    path = _seed_file(integration_vault, "fm-noop.md", NOTE_CONTENT)
    before = path.read_text(encoding="utf-8")
    recorder = SnapshotRecorder("15-delete-frontmatter-field-noop", integration_vault)
    recorder.capture_before("fm-noop.md")

    integration_api.delete_frontmatter_field("fm-noop.md", "nonexistent")
    recorder.capture_after("fm-noop.md")

    after = path.read_text(encoding="utf-8")
    assert after == before
    _record_report(
        integration_report,
        "15 — Delete Frontmatter Field (No-op)",
        'vault.delete_frontmatter_field("fm-noop.md", "nonexistent")',
        "PASS",
    )


def test_16_read_heading(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    _seed_file(integration_vault, "cp-heading.md", NOTE_CONTENT)
    recorder = SnapshotRecorder("16-read-heading", integration_vault)
    recorder.capture_before("cp-heading.md")

    content = integration_api.read_heading("cp-heading.md", "## Agenda")
    recorder.write_result(content or "")
    recorder.capture_after("cp-heading.md")

    assert content is not None
    assert "- Review sprint progress" in content
    assert "### Action Items" in content
    _record_report(
        integration_report,
        "16 — Read Heading",
        'vault.read_heading("cp-heading.md", "## Agenda")',
        "PASS",
    )


def test_17_write_heading_replace(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    path = _seed_file(integration_vault, "cp-heading.md", NOTE_CONTENT)
    recorder = SnapshotRecorder("17-write-heading-replace", integration_vault)
    recorder.capture_before("cp-heading.md")

    integration_api.write_heading("cp-heading.md", "## Notes", "Replaced notes.\n")
    recorder.capture_after("cp-heading.md")

    text = path.read_text(encoding="utf-8")
    assert "Replaced notes.\n" in text
    assert "Key discussion points from the meeting." not in text
    assert "## References" in text
    notes_start = text.index("## Notes\n")
    refs_start = text.index("## References\n")
    notes_section = text[notes_start:refs_start]
    assert "Replaced notes." in notes_section
    _record_report(
        integration_report,
        "17 — Write Heading (Replace)",
        'vault.write_heading("cp-heading.md", "## Notes", "Replaced notes.\\n")',
        "PASS",
    )


def test_18_write_heading_append(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    path = _seed_file(integration_vault, "cp-append.md", NOTE_CONTENT)
    recorder = SnapshotRecorder("18-write-heading-append", integration_vault)
    recorder.capture_before("cp-append.md")

    integration_api.write_heading("cp-append.md", "## New Section", "Appended content.\n")
    recorder.capture_after("cp-append.md")

    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n\n## New Section\nAppended content.\n")
    assert "# Meeting Notes" in text
    _record_report(
        integration_report,
        "18 — Write Heading (Append)",
        'vault.write_heading("cp-append.md", "## New Section", "Appended content.\\n")',
        "PASS",
    )


def test_19_read_block(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    _seed_file(integration_vault, "cp-block.md", NOTE_CONTENT)
    recorder = SnapshotRecorder("19-read-block", integration_vault)
    recorder.capture_before("cp-block.md")

    content = integration_api.read_block("cp-block.md", "^meeting-notes")
    recorder.write_result(content or "")
    recorder.capture_after("cp-block.md")

    assert content is not None
    assert "The team agreed on the new timeline. ^meeting-notes" in content
    _record_report(
        integration_report,
        "19 — Read Block",
        'vault.read_block("cp-block.md", "^meeting-notes")',
        "PASS",
    )


def test_20_write_block(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    path = _seed_file(integration_vault, "cp-block.md", NOTE_CONTENT)
    recorder = SnapshotRecorder("20-write-block", integration_vault)
    recorder.capture_before("cp-block.md")

    integration_api.write_block("cp-block.md", "^ref-block", "Updated reference paragraph. ^ref-block\n")
    recorder.capture_after("cp-block.md")

    text = path.read_text(encoding="utf-8")
    assert "Updated reference paragraph. ^ref-block" in text
    assert "Some reference paragraph. ^ref-block" not in text
    _record_report(
        integration_report,
        "20 — Write Block",
        'vault.write_block("cp-block.md", "^ref-block", "Updated reference paragraph. ^ref-block\\n")',
        "PASS",
    )


def test_21_write_block_list_item(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    path = _seed_file(integration_vault, "cp-list.md", NOTE_CONTENT)
    recorder = SnapshotRecorder("21-write-block-list-item", integration_vault)
    recorder.capture_before("cp-list.md")

    integration_api.write_block("cp-list.md", "^list-ref", "- Updated action item ^list-ref\n")
    recorder.capture_after("cp-list.md")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert "- Updated action item ^list-ref" in lines
    assert "- First item" in lines
    assert "- Third item" in lines
    _record_report(
        integration_report,
        "21 — Write Block (List Item)",
        'vault.write_block("cp-list.md", "^list-ref", "- Updated action item ^list-ref\\n")',
        "PASS",
    )


def test_22_error_path_escape(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    recorder = SnapshotRecorder("22-error-path-escape", integration_vault)
    with pytest.raises(PathError, match="traversal|not allowed") as exc_info:
        integration_api.read_file("../../etc/passwd")
    recorder.write_error(exc_info.value)
    _record_report(
        integration_report,
        "22 — Error: Path Escape",
        'vault.read_file("../../etc/passwd")',
        "PASS (raised PathError)",
    )


def test_23_error_absolute_path(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    recorder = SnapshotRecorder("23-error-absolute-path", integration_vault)
    with pytest.raises(PathError, match="absolute") as exc_info:
        integration_api.read_file("/etc/passwd")
    recorder.write_error(exc_info.value)
    _record_report(
        integration_report,
        "23 — Error: Absolute Path",
        'vault.read_file("/etc/passwd")',
        "PASS (raised PathError)",
    )


def test_24_error_empty_path(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    recorder = SnapshotRecorder("24-error-empty-path", integration_vault)
    with pytest.raises(PathError, match="empty") as exc_info:
        integration_api.read_file("")
    recorder.write_error(exc_info.value)
    _record_report(
        integration_report,
        "24 — Error: Empty Path",
        'vault.read_file("")',
        "PASS (raised PathError)",
    )


def test_25_error_file_not_found(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    recorder = SnapshotRecorder("25-error-file-not-found", integration_vault)
    with pytest.raises(FileNotFoundError) as exc_info:
        integration_api.read_file("nonexistent.md")
    recorder.write_error(exc_info.value)
    _record_report(
        integration_report,
        "25 — Error: Missing File",
        'vault.read_file("nonexistent.md")',
        "PASS (raised FileNotFoundError)",
    )


def test_26_error_file_too_large(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    recorder = SnapshotRecorder("26-error-file-too-large", integration_vault)
    with pytest.raises(FileTooLargeError) as exc_info:
        integration_api.read_file("large-file.md")
    recorder.write_error(exc_info.value)
    _record_report(
        integration_report,
        "26 — Error: File Too Large",
        'vault.read_file("large-file.md")',
        "PASS (raised FileTooLargeError)",
    )


def test_27_error_block_not_found(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    _seed_file(integration_vault, "note.md", NOTE_CONTENT)
    recorder = SnapshotRecorder("27-error-block-not-found", integration_vault)
    with pytest.raises(ContentPatchError, match="not found") as exc_info:
        integration_api.write_block("note.md", "^missing", "x")
    recorder.write_error(exc_info.value)
    _record_report(
        integration_report,
        "27 — Error: Block Not Found",
        'vault.write_block("note.md", "^missing", "x")',
        "PASS (raised ContentPatchError)",
    )


def test_28_error_malformed_frontmatter(
    integration_api: Vault, integration_vault: Path, integration_report: ReportWriter
) -> None:
    _seed_file(integration_vault, "bad-yaml.md", "---\n: [invalid\n---\n")
    recorder = SnapshotRecorder("28-error-malformed-frontmatter", integration_vault)
    with pytest.raises(FrontmatterError) as exc_info:
        integration_api.get_frontmatter("bad-yaml.md")
    recorder.write_error(exc_info.value)
    _record_report(
        integration_report,
        "28 — Error: Malformed Frontmatter",
        'vault.get_frontmatter("bad-yaml.md")',
        "PASS (raised FrontmatterError)",
    )


def test_29_is_busy(integration_api: Vault, integration_vault: Path, integration_report: ReportWriter) -> None:
    recorder = SnapshotRecorder("29-is-busy", integration_vault)
    busy = integration_api.is_busy()
    recorder.write_result(str(busy))
    assert busy is False
    _record_report(integration_report, "29 — Is Busy", "vault.is_busy()", "PASS")
