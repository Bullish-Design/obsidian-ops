"""Vault primary API."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from obsidian_ops.anchors import EnsureBlockResult, ensure_block_result
from obsidian_ops.content import find_block, find_heading, normalize_patch_content
from obsidian_ops.errors import ContentPatchError, FileTooLargeError, VaultError, VCSError
from obsidian_ops.frontmatter import merge_frontmatter, parse_frontmatter, serialize_frontmatter
from obsidian_ops.lock import MutationLock
from obsidian_ops.sandbox import validate_path
from obsidian_ops.search import SearchResult, search_content, walk_vault
from obsidian_ops.structure import StructureView, parse_structure
from obsidian_ops.templates import (
    CreatePageResult,
    TemplateDefinition,
    create_from_template,
    list_templates,
)
from obsidian_ops.vcs import JJ, ReadinessCheck, SyncResult, UndoResult, VCSReadiness

MAX_READ_SIZE = 512 * 1024
MAX_LIST_RESULTS = 200
MAX_SEARCH_RESULTS = 50
SNIPPET_CONTEXT = 80
LOGGER = logging.getLogger(__name__)


class Vault:
    """Sandboxed API for interacting with an Obsidian vault."""

    def __init__(self, root: str | Path, *, jj_bin: str = "jj", jj_timeout: int = 120) -> None:
        root_path = Path(root)
        if not root_path.exists():
            raise VaultError(f"vault root does not exist: {root}")
        if not root_path.is_dir():
            raise VaultError(f"vault root is not a directory: {root}")

        self.root = Path(os.path.realpath(root_path))
        self._lock = MutationLock()
        self.jj_bin = jj_bin
        self.jj_timeout = jj_timeout
        self._jj: JJ | None = None

    def _get_jj(self) -> JJ:
        if self._jj is None:
            self._jj = JJ(self.root, jj_bin=self.jj_bin, timeout=self.jj_timeout)
        return self._jj

    def read_file(self, path: str) -> str:
        abs_path = validate_path(self.root, path)
        if not abs_path.exists():
            raise FileNotFoundError(path)
        if abs_path.stat().st_size > MAX_READ_SIZE:
            raise FileTooLargeError(f"file exceeds max read size: {path}")
        return abs_path.read_text(encoding="utf-8")

    def _unsafe_write_file(self, path: str, content: str) -> None:
        abs_path = validate_path(self.root, path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        with self._lock:
            self._unsafe_write_file(path, content)

    def _unsafe_delete_file(self, path: str) -> None:
        abs_path = validate_path(self.root, path)
        abs_path.unlink()

    def delete_file(self, path: str) -> None:
        with self._lock:
            self._unsafe_delete_file(path)

    def list_files(self, pattern: str = "*.md", *, max_results: int = MAX_LIST_RESULTS) -> list[str]:
        return walk_vault(self.root, pattern, max_results=max_results)

    def search_files(
        self,
        query: str,
        *,
        glob: str = "*.md",
        max_results: int = MAX_SEARCH_RESULTS,
    ) -> list[SearchResult]:
        files = self.list_files(glob, max_results=MAX_LIST_RESULTS)
        return search_content(self.root, query, files, max_results=max_results)

    def list_structure(self, path: str) -> StructureView:
        text = self.read_file(path)
        return parse_structure(path, text)

    def get_frontmatter(self, path: str) -> dict[str, Any] | None:
        text = self.read_file(path)
        data, _body = parse_frontmatter(text)
        return data

    def set_frontmatter(self, path: str, data: dict[str, Any]) -> None:
        with self._lock:
            text = self.read_file(path)
            _existing, body = parse_frontmatter(text)
            updated_text = serialize_frontmatter(data, body)
            self._unsafe_write_file(path, updated_text)

    def update_frontmatter(self, path: str, updates: dict[str, Any]) -> None:
        with self._lock:
            text = self.read_file(path)
            existing, body = parse_frontmatter(text)
            merged = merge_frontmatter(existing, updates)
            updated_text = serialize_frontmatter(merged, body)
            self._unsafe_write_file(path, updated_text)

    def delete_frontmatter_field(self, path: str, field: str) -> None:
        with self._lock:
            text = self.read_file(path)
            existing, body = parse_frontmatter(text)
            if existing is None:
                return
            if field not in existing:
                return

            updated = dict(existing)
            updated.pop(field, None)

            updated_text = serialize_frontmatter(updated, body)
            self._unsafe_write_file(path, updated_text)

    def read_heading(self, path: str, heading: str) -> str | None:
        text = self.read_file(path)
        bounds = find_heading(text, heading)
        if bounds is None:
            return None
        start, end = bounds
        return text[start:end]

    def write_heading(self, path: str, heading: str, content: str) -> None:
        with self._lock:
            text = self.read_file(path)
            bounds = find_heading(text, heading)
            normalized_content = normalize_patch_content(content)
            if bounds is None:
                base = text
                if base and not base.endswith("\n"):
                    base += "\n"
                if base and not base.endswith("\n\n"):
                    base += "\n"
                replacement = f"{base}{heading}\n{normalized_content}"
            else:
                start, end = bounds
                replacement = f"{text[:start]}{normalized_content}{text[end:]}"
            self._unsafe_write_file(path, replacement)

    def read_block(self, path: str, block_id: str) -> str | None:
        text = self.read_file(path)
        bounds = find_block(text, block_id)
        if bounds is None:
            return None
        start, end = bounds
        return text[start:end]

    def write_block(self, path: str, block_id: str, content: str) -> None:
        with self._lock:
            text = self.read_file(path)
            bounds = find_block(text, block_id)
            if bounds is None:
                raise ContentPatchError(f"block reference not found: {block_id}")
            start, end = bounds
            replacement = normalize_patch_content(content)
            updated_text = f"{text[:start]}{replacement}{text[end:]}"
            self._unsafe_write_file(path, updated_text)

    def ensure_block_id(self, path: str, line_start: int, line_end: int) -> EnsureBlockResult:
        with self._lock:
            text = self.read_file(path)
            result, final_text = ensure_block_result(path, text, line_start, line_end)
            if result.created:
                self._unsafe_write_file(path, final_text)
            return result

    def list_templates(self) -> list[TemplateDefinition]:
        return list_templates(self.root)

    def create_from_template(self, template_id: str, fields: dict[str, str]) -> CreatePageResult:
        with self._lock:
            templates = list_templates(self.root)
            result, body, commit_message = create_from_template(self.root, templates, template_id, fields)
            self._unsafe_write_file(result.path, body)

            jj = self._get_jj()
            jj.describe(commit_message)
            jj.new()

            return result

    def commit(self, message: str) -> None:
        with self._lock:
            jj = self._get_jj()
            jj.describe(message)
            jj.new()

    def undo(self) -> None:
        with self._lock:
            self._get_jj().undo()

    def undo_last_change(self) -> UndoResult:
        with self._lock:
            jj = self._get_jj()
            jj.undo()
            try:
                jj.restore_from_previous()
            except VCSError as exc:
                return UndoResult(restored=False, warning=f"restore after undo failed: {exc}")
            return UndoResult(restored=True)

    def vcs_status(self) -> str:
        return self._get_jj().status()

    def _is_git_dirty(self, root: Path) -> bool:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise VCSError(f"git status failed during readiness check: {result.stderr.strip()}")
        return bool((result.stdout or "").strip())

    def check_sync_readiness(self) -> ReadinessCheck:
        jj_dir = self.root / ".jj"
        git_dir = self.root / ".git"

        try:
            has_jj = jj_dir.exists()
            has_git = git_dir.exists()

            if has_jj:
                try:
                    remotes_output = self._get_jj().git_remote_list()
                except VCSError:
                    if has_git:
                        detail = "colocated state needs verification"
                        LOGGER.info("Sync readiness requires migration: %s", detail)
                        return ReadinessCheck(status=VCSReadiness.MIGRATION_NEEDED, detail=detail)
                    raise
                remotes = [line.strip() for line in remotes_output.splitlines() if line.strip()]
                if remotes:
                    return ReadinessCheck(status=VCSReadiness.READY)
                return ReadinessCheck(status=VCSReadiness.READY, detail="no remote configured")

            if not has_git:
                detail = "no vcs initialized"
                LOGGER.info("Sync readiness requires migration: %s", detail)
                return ReadinessCheck(status=VCSReadiness.MIGRATION_NEEDED, detail=detail)

            if self._is_git_dirty(self.root):
                detail = "git-only with uncommitted changes"
                LOGGER.info("Sync readiness requires migration: %s", detail)
                return ReadinessCheck(status=VCSReadiness.MIGRATION_NEEDED, detail=detail)

            detail = "git-only, safe to colocate"
            LOGGER.info("Sync readiness requires migration: %s", detail)
            return ReadinessCheck(status=VCSReadiness.MIGRATION_NEEDED, detail=detail)
        except Exception as exc:  # pragma: no cover - defensive classification guard
            LOGGER.exception("Sync readiness check failed")
            return ReadinessCheck(status=VCSReadiness.ERROR, detail=str(exc))

    def ensure_sync_ready(self) -> ReadinessCheck:
        readiness = self.check_sync_readiness()
        if readiness.status in {VCSReadiness.READY, VCSReadiness.ERROR}:
            return readiness

        if readiness.detail in {"no vcs initialized", "git-only, safe to colocate"}:
            with self._lock:
                self._get_jj().git_init_colocate()
            return self.check_sync_readiness()

        LOGGER.info("Sync readiness not auto-fixed: %s", readiness.detail)
        return readiness

    def _sync_metadata_dir(self) -> Path:
        return self.root / ".forge"

    def _sync_state_path(self) -> Path:
        return self._sync_metadata_dir() / "sync-state.json"

    def _credential_helper_path(self) -> Path:
        return self._sync_metadata_dir() / "git-credential.sh"

    def _sync_env(self) -> dict[str, str] | None:
        helper = self._credential_helper_path()
        if not helper.exists():
            return None
        return {"GIT_ASKPASS": str(helper), "GIT_TERMINAL_PROMPT": "0"}

    def _validate_remote_url(self, url: str) -> None:
        parsed = urlparse(url)
        is_http_like = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        is_file_like = parsed.scheme == "file" and bool(parsed.path)
        is_git_ssh = url.startswith("git@") and ":" in url
        if not (is_http_like or is_file_like or is_git_ssh):
            raise VCSError(f"invalid sync remote URL: {url}")

    def _write_credential_helper(self, token: str) -> None:
        helper = self._credential_helper_path()
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(
            "#!/bin/sh\n"
            f"echo \"password={token}\"\n"
            "echo \"username=x-access-token\"\n",
            encoding="utf-8",
        )
        helper.chmod(0o700)

    def _clear_credential_helper(self) -> None:
        helper = self._credential_helper_path()
        if helper.exists():
            helper.unlink()

    def _now_iso(self) -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat()

    def _write_sync_state(self, payload: dict[str, Any]) -> None:
        path = self._sync_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(path)

    def _read_sync_state(self) -> dict[str, Any]:
        path = self._sync_state_path()
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _has_rebase_conflict(self) -> bool:
        output = self._get_jj().log(revset="@", template="description")
        return "conflict" in output.lower()

    def _create_conflict_bookmark(self, prefix: str) -> str:
        ts = self._now_iso().replace(":", "-").replace("+00:00", "Z")
        name = f"{prefix}/{ts}"
        self._get_jj().bookmark_create(name, revision="@")
        return name

    def _ensure_main_bookmark(self) -> str:
        jj = self._get_jj()
        try:
            jj.bookmark_create("main", revision="@-")
        except VCSError as exc:
            if "already exists" not in str(exc).lower():
                raise
        return "main"

    def configure_sync_remote(self, url: str, *, token: str | None = None, remote: str = "origin") -> None:
        with self._lock:
            self._validate_remote_url(url)
            readiness = self.ensure_sync_ready()
            if readiness.status != VCSReadiness.READY:
                raise VCSError(f"sync workspace not ready: {readiness.detail or readiness.status.value}")

            if token is None:
                self._clear_credential_helper()
            else:
                self._write_credential_helper(token)

            jj = self._get_jj()
            try:
                jj.git_remote_add(remote, url)
            except VCSError as exc:
                if "already exists" not in str(exc).lower():
                    raise
                jj.git_remote_set_url(remote, url)

    def sync_fetch(self, *, remote: str = "origin") -> None:
        readiness = self.ensure_sync_ready()
        if readiness.status != VCSReadiness.READY:
            raise VCSError(f"sync workspace not ready: {readiness.detail or readiness.status.value}")
        self._get_jj().git_fetch(remote=remote, env=self._sync_env())

    def sync_push(self, *, remote: str = "origin") -> None:
        readiness = self.ensure_sync_ready()
        if readiness.status != VCSReadiness.READY:
            raise VCSError(f"sync workspace not ready: {readiness.detail or readiness.status.value}")
        bookmark = self._ensure_main_bookmark()
        self._get_jj().git_push(remote=remote, bookmark=bookmark, allow_new=True, env=self._sync_env())

    def sync(self, *, remote: str = "origin", conflict_prefix: str = "sync-conflict") -> SyncResult:
        readiness = self.ensure_sync_ready()
        if readiness.status != VCSReadiness.READY:
            return SyncResult(ok=False, error=f"sync workspace not ready: {readiness.detail or readiness.status.value}")

        jj = self._get_jj()
        env = self._sync_env()

        try:
            jj.git_fetch(remote=remote, env=env)
            jj.rebase(destination="trunk()")

            if self._has_rebase_conflict():
                bookmark = self._create_conflict_bookmark(conflict_prefix)
                jj.git_push(remote=remote, bookmark=bookmark, allow_new=True, env=env)
                self._write_sync_state(
                    {
                        "last_sync_at": self._now_iso(),
                        "last_sync_ok": False,
                        "conflict_active": True,
                        "conflict_bookmark": bookmark,
                    }
                )
                return SyncResult(ok=False, conflict=True, conflict_bookmark=bookmark)

            bookmark = self._ensure_main_bookmark()
            jj.git_push(remote=remote, bookmark=bookmark, allow_new=True, env=env)
            self._write_sync_state(
                {
                    "last_sync_at": self._now_iso(),
                    "last_sync_ok": True,
                    "conflict_active": False,
                    "conflict_bookmark": None,
                }
            )
            return SyncResult(ok=True)
        except VCSError as exc:
            self._write_sync_state(
                {
                    "last_sync_at": self._now_iso(),
                    "last_sync_ok": False,
                    "conflict_active": False,
                    "conflict_bookmark": None,
                }
            )
            return SyncResult(ok=False, error=str(exc))

    def sync_status(self) -> dict[str, Any]:
        return self._read_sync_state()

    def is_busy(self) -> bool:
        return self._lock.is_held
