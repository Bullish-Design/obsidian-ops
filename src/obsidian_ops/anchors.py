"""Helpers for ensuring stable markdown block anchors."""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass

from obsidian_ops.errors import ContentPatchError

_EXISTING_ANCHOR_RE = re.compile(r"\^([A-Za-z0-9][A-Za-z0-9_-]{0,63})\s*$")


@dataclass(frozen=True)
class EnsureBlockResult:
    path: str
    block_id: str
    created: bool
    line_start: int
    line_end: int
    sha256: str


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_range(line_start: int, line_end: int, total_lines: int) -> tuple[int, int]:
    if total_lines == 0:
        raise ContentPatchError("cannot ensure block id in an empty file")
    if line_start < 1 or line_end < 1:
        raise ContentPatchError("line range must be 1-based and positive")
    if line_start > line_end:
        raise ContentPatchError("line_start must be <= line_end")
    if line_end > total_lines:
        raise ContentPatchError("line range exceeds file length")
    return line_start, line_end


def _extract_existing_anchor(lines: list[str], line_start: int, line_end: int) -> str | None:
    for idx in range(line_start - 1, line_end):
        stripped = lines[idx].rstrip("\r\n")
        match = _EXISTING_ANCHOR_RE.search(stripped)
        if match is not None:
            return match.group(1)
    return None


def _choose_anchor_line(lines: list[str], line_start: int, line_end: int) -> int:
    for idx in range(line_end - 1, line_start - 2, -1):
        if lines[idx].strip() != "":
            return idx
    raise ContentPatchError("target range has no non-empty line")


def _append_anchor(line: str, block_id: str) -> str:
    newline = ""
    body = line
    if line.endswith("\r\n"):
        newline = "\r\n"
        body = line[:-2]
    elif line.endswith("\n"):
        newline = "\n"
        body = line[:-1]

    if body and not body.endswith(" "):
        body += " "

    body += f"^{block_id}"
    return body + newline


def ensure_block_result(path: str, text: str, line_start: int, line_end: int) -> tuple[EnsureBlockResult, str]:
    lines = text.splitlines(keepends=True)
    line_start, line_end = _normalize_range(line_start, line_end, len(lines))

    existing = _extract_existing_anchor(lines, line_start, line_end)
    if existing is not None:
        result = EnsureBlockResult(
            path=path,
            block_id=existing,
            created=False,
            line_start=line_start,
            line_end=line_end,
            sha256=_sha256(text),
        )
        return result, text

    target_idx = _choose_anchor_line(lines, line_start, line_end)
    block_id = f"forge-{secrets.token_hex(3)}"
    lines[target_idx] = _append_anchor(lines[target_idx], block_id)
    updated = "".join(lines)

    result = EnsureBlockResult(
        path=path,
        block_id=block_id,
        created=True,
        line_start=line_start,
        line_end=target_idx + 1,
        sha256=_sha256(updated),
    )
    return result, updated
