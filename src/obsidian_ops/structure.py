"""Markdown structure extraction for headings and block anchors."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)?\s*$")
_BLOCK_ID_RE = re.compile(r"\^([A-Za-z0-9][A-Za-z0-9_-]{0,63})\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*([*+-]\s|\d+[.)]\s)")


@dataclass(frozen=True)
class Heading:
    text: str
    level: int
    line_start: int
    line_end: int


@dataclass(frozen=True)
class Block:
    block_id: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class StructureView:
    path: str
    sha256: str
    headings: list[Heading]
    blocks: list[Block]


def _split_lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _is_heading(line: str) -> tuple[int, str] | None:
    match = _HEADING_RE.match(line.rstrip("\r\n"))
    if match is None:
        return None
    level = len(match.group(1))
    heading_text = match.group(0).rstrip()
    return level, heading_text


def _extract_headings(lines: list[str]) -> list[Heading]:
    markers: list[tuple[int, int, str]] = []  # (line_number, level, text)

    for index, line in enumerate(lines, start=1):
        parsed = _is_heading(line)
        if parsed is None:
            continue
        level, heading_text = parsed
        markers.append((index, level, heading_text))

    if not markers:
        return []

    result: list[Heading] = []
    last_line = len(lines)

    for idx, (line_start, level, heading_text) in enumerate(markers):
        line_end = last_line
        for follow_start, follow_level, _follow_text in markers[idx + 1 :]:
            if follow_level <= level:
                line_end = follow_start - 1
                break

        result.append(
            Heading(
                text=heading_text,
                level=level,
                line_start=line_start,
                line_end=line_end,
            )
        )

    return result


def _extract_blocks(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []

    for index, line in enumerate(lines, start=1):
        stripped = line.rstrip("\r\n")
        match = _BLOCK_ID_RE.search(stripped)
        if match is None:
            continue

        block_id = match.group(1)
        line_start = index

        # List items are single-line blocks for anchor scoping.
        if not _LIST_ITEM_RE.match(stripped):
            while line_start > 1:
                prev = lines[line_start - 2].strip()
                if prev == "":
                    break
                if _is_heading(lines[line_start - 2]) is not None:
                    break
                line_start -= 1

        blocks.append(Block(block_id=block_id, line_start=line_start, line_end=index))

    return blocks


def parse_structure(path: str, text: str) -> StructureView:
    lines = _split_lines(text)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    return StructureView(
        path=path,
        sha256=digest,
        headings=_extract_headings(lines),
        blocks=_extract_blocks(lines),
    )
