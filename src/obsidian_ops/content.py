"""Content patching helpers for headings and block references."""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#+)\s")


def _line_offsets(text: str) -> tuple[list[str], list[int]]:
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)
    return lines, offsets


def _line_content(line: str) -> str:
    return line.rstrip("\r\n")


def _heading_level(heading_line: str) -> int | None:
    match = _HEADING_RE.match(heading_line)
    if match is None:
        return None
    return len(match.group(1))


def find_heading(text: str, heading: str) -> tuple[int, int] | None:
    """Find content bounds for a heading section."""
    lines, offsets = _line_offsets(text)
    target = heading.rstrip()

    for index, line in enumerate(lines):
        normalized = _line_content(line).rstrip()
        if normalized != target:
            continue

        current_level = _heading_level(normalized)
        if current_level is None:
            continue

        start = offsets[index] + len(line)
        end = len(text)

        for follow_idx in range(index + 1, len(lines)):
            follow_line = _line_content(lines[follow_idx]).rstrip()
            follow_level = _heading_level(follow_line)
            if follow_level is not None and follow_level <= current_level:
                end = offsets[follow_idx]
                break

        return start, end

    return None


def find_block(text: str, block_id: str) -> tuple[int, int] | None:
    """Find paragraph/list-item bounds for a block reference."""
    token_re = re.compile(rf"(?<!\\S){re.escape(block_id)}(?!\\S)")
    lines, offsets = _line_offsets(text)

    for index, line in enumerate(lines):
        line_text = _line_content(line)
        if token_re.search(line_text) is None:
            continue

        stripped = line_text.lstrip()
        is_list_item = bool(re.match(r"([*+-]\s|\d+[.)]\s)", stripped))
        if is_list_item:
            start_line = index
        else:
            start_line = index
            while start_line > 0 and _line_content(lines[start_line - 1]).strip() != "":
                start_line -= 1

        start = offsets[start_line]
        end = offsets[index] + len(line)
        return start, end

    return None
