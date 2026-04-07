"""Frontmatter parsing and serialization helpers."""

from __future__ import annotations

import re
from typing import Any

import yaml

from obsidian_ops.errors import FrontmatterError

_OPENING_RE = re.compile(r"^(?:\ufeff)?[\t \r\n]*---[ \t]*\r?\n")
_CLOSING_RE = re.compile(r"(?m)^---[ \t]*\r?$")


class _NoTimestampSafeLoader(yaml.SafeLoader):
    """Safe loader variant that keeps timestamp-looking scalars as strings."""


for first_char, resolvers in list(_NoTimestampSafeLoader.yaml_implicit_resolvers.items()):
    _NoTimestampSafeLoader.yaml_implicit_resolvers[first_char] = [
        resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:timestamp"
    ]


def parse_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Parse YAML frontmatter from text and return (frontmatter, body)."""
    opening = _OPENING_RE.match(text)
    if opening is None:
        return None, text

    yaml_start = opening.end()
    closing = _CLOSING_RE.search(text, yaml_start)
    if closing is None:
        raise FrontmatterError("frontmatter opening delimiter found without closing delimiter")

    yaml_text = text[yaml_start : closing.start()]

    body_start = closing.end()
    if text.startswith("\r\n", body_start):
        body_start += 2
    elif text.startswith("\n", body_start):
        body_start += 1

    body = text[body_start:]

    try:
        loaded = yaml.load(yaml_text, Loader=_NoTimestampSafeLoader) if yaml_text.strip() else {}
    except yaml.YAMLError as exc:
        raise FrontmatterError("invalid frontmatter YAML") from exc

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise FrontmatterError("frontmatter must deserialize to a mapping")

    return loaded, body


def serialize_frontmatter(data: dict[str, Any], body: str) -> str:
    """Serialize frontmatter data plus body content."""
    yaml_text = yaml.safe_dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False).rstrip("\n")
    return f"---\n{yaml_text}\n---\n{body}"
