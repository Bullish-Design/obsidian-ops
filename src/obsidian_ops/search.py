"""Vault listing and content search utilities."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

MAX_READ_SIZE = 512 * 1024
SNIPPET_CONTEXT = 80


@dataclass(frozen=True)
class SearchResult:
    path: str
    snippet: str


def walk_vault(root: Path, pattern: str, max_results: int) -> list[str]:
    """Return sorted vault-relative file paths matching a relative-path glob."""
    if max_results <= 0:
        return []

    matches: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue

        rel_path = path.relative_to(root)
        if any(part.startswith(".") or part.startswith("_hidden_") for part in rel_path.parts):
            continue

        rel_path_str = rel_path.as_posix()
        if fnmatch(rel_path_str, pattern):
            matches.append(rel_path_str)

    matches.sort()
    return matches[:max_results]


def _snippet_for(text: str, match_index: int, query_len: int) -> str:
    start = max(0, match_index - SNIPPET_CONTEXT)
    end = min(len(text), match_index + query_len + SNIPPET_CONTEXT)
    return text[start:end]


def search_content(root: Path, query: str, files: list[str], max_results: int) -> list[SearchResult]:
    """Search files for a case-insensitive query and return contextual snippets."""
    if not query or max_results <= 0:
        return []

    needle = query.casefold()
    results: list[SearchResult] = []

    for rel_path_str in files:
        path = root / rel_path_str
        if not path.exists() or not path.is_file():
            continue
        if path.stat().st_size > MAX_READ_SIZE:
            continue

        text = path.read_text(encoding="utf-8")
        index = text.casefold().find(needle)
        if index == -1:
            continue

        results.append(SearchResult(path=rel_path_str, snippet=_snippet_for(text, index, len(query))))
        if len(results) >= max_results:
            break

    return results
