"""Vault primary API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from obsidian_ops.errors import FileTooLargeError, VaultError
from obsidian_ops.frontmatter import parse_frontmatter, serialize_frontmatter
from obsidian_ops.lock import MutationLock
from obsidian_ops.sandbox import validate_path
from obsidian_ops.search import SearchResult, search_content, walk_vault

MAX_READ_SIZE = 512 * 1024
MAX_LIST_RESULTS = 200
MAX_SEARCH_RESULTS = 50
SNIPPET_CONTEXT = 80


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
        files = walk_vault(self.root, glob, max_results=MAX_LIST_RESULTS)
        return search_content(self.root, query, files, max_results=max_results)

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

            merged = dict(existing or {})
            merged.update(updates)

            updated_text = serialize_frontmatter(merged, body)
            self._unsafe_write_file(path, updated_text)

    def delete_frontmatter_field(self, path: str, field: str) -> None:
        with self._lock:
            text = self.read_file(path)
            existing, body = parse_frontmatter(text)
            if existing is None:
                return

            updated = dict(existing)
            updated.pop(field, None)

            updated_text = serialize_frontmatter(updated, body)
            self._unsafe_write_file(path, updated_text)

    def is_busy(self) -> bool:
        return self._lock.is_held
