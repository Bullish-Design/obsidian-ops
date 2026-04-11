# OBSIDIAN_OPS_EXPANSION_IMPLEMENTATION_GUIDE.md

## Audience

This guide is for engineers implementing the `obsidian-ops` library expansion
for structure introspection, stable block anchors, and deterministic
template-based page creation.

## Scope

This document covers `obsidian-ops` only. It intentionally does **not** include
FastAPI route wiring (that belongs in obsidian-agent).

## Table of contents

1. Implementation contract and guardrails
   - Non-negotiable architectural boundaries and coding constraints.
2. Prerequisites and baseline checks
   - Environment sync, test baseline, and JJ fixture setup.
3. Phase 0.1: markdown structure primitive
   - Add `Heading`, `Block`, `StructureView` and deterministic parsing.
4. Phase 0.2: idempotent block anchor primitive
   - Add `ensure_block_id` behavior with lock-safe writes.
5. Phase 0.3: vault-local templates and page creation
   - Add template discovery/rendering and `create_from_template`.
6. Phase 0.4: integration and export wiring
   - Update `Vault`, package exports, and module boundaries.
7. Test plan by phase
   - Exact tests for each new primitive and edge case.
8. Final validation gate
   - Full commands for lint, types, tests, and coverage.
9. Hand-off checklist for obsidian-agent
   - Stable contracts required by downstream route wiring.

## 1) Implementation Contract and Guardrails

1. `obsidian-ops` remains a library-first package.
2. No FastAPI route code lands under `src/obsidian_ops/` for this work.
3. All writes go through `Vault` and stay protected by `MutationLock`.
4. Every user path must be validated via `validate_path()` before read/write.
5. Reuse current error model (`PathError`, `ContentPatchError`, `VCSError`, etc.)
   instead of introducing parallel exception types.
6. New primitives must be composable so obsidian-agent route handlers can call
   them directly with thin request/response mapping.

## 2) Prerequisites and Baseline Checks

Run these commands from repo root.

```bash
devenv shell -- uv sync --extra dev
devenv shell -- pytest tests -q
devenv shell -- ruff check src tests
```

If you will validate `create_from_template` commit behavior with real JJ,
initialize a fixture vault exactly like this:

```bash
mkdir -p /tmp/ops-template-vault
cd /tmp/ops-template-vault
jj git init
printf '# Seed\n' > seed.md
jj describe -m 'seed'
jj new
```

## 3) Phase 0.1: Markdown Structure Primitive

### 3.1 Create `src/obsidian_ops/structure.py`

Add a dedicated module for deterministic markdown structure extraction.

```python
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

        # List items are single-line blocks for anchor-scoping.
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
```

### 3.2 Wire it into `Vault`

Update `src/obsidian_ops/vault.py` imports:

```python
from obsidian_ops.structure import StructureView, parse_structure
```

Add method on `Vault`:

```python
def list_structure(self, path: str) -> StructureView:
    text = self.read_file(path)
    return parse_structure(path, text)
```

### 3.3 Export new model types

Update `src/obsidian_ops/__init__.py`:

```python
from obsidian_ops.structure import Block, Heading, StructureView

__all__ = [
    # existing exports...
    "Heading",
    "Block",
    "StructureView",
]
```

### 3.4 Add tests (`tests/test_structure.py`)

```python
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from obsidian_ops.errors import PathError
from obsidian_ops.vault import Vault


def test_mixed_heading_levels_have_correct_ranges(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "doc.md").write_text(
        "# Top\n\n## One\nBody 1\n\n### Nested\nNested body\n\n## Two\nBody 2\n",
        encoding="utf-8",
    )

    view = Vault(root).list_structure("doc.md")

    assert [h.text for h in view.headings] == ["# Top", "## One", "### Nested", "## Two"]
    assert [(h.text, h.line_start, h.line_end) for h in view.headings] == [
        ("# Top", 1, 10),
        ("## One", 3, 8),
        ("### Nested", 6, 8),
        ("## Two", 9, 10),
    ]


def test_multiline_paragraph_anchor_has_correct_span(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    text = "# Note\n\nLine a\nLine b\nLine c ^anchor-1\n\nTail\n"
    (root / "note.md").write_text(text, encoding="utf-8")

    view = Vault(root).list_structure("note.md")

    assert len(view.blocks) == 1
    block = view.blocks[0]
    assert block.block_id == "anchor-1"
    assert (block.line_start, block.line_end) == (3, 5)


def test_empty_file_returns_valid_structure_and_hash(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "empty.md").write_text("", encoding="utf-8")

    view = Vault(root).list_structure("empty.md")

    assert view.path == "empty.md"
    assert view.headings == []
    assert view.blocks == []
    assert view.sha256 == hashlib.sha256(b"").hexdigest()


def test_list_structure_rejects_path_escape(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    with pytest.raises(PathError):
        vault.list_structure("../outside.md")
```

### 3.5 Phase 0.1 gate

```bash
devenv shell -- pytest tests/test_structure.py -v
devenv shell -- pytest tests/test_vault.py tests/test_sandbox.py -q
```

## 4) Phase 0.2: Idempotent Block Anchor Primitive

### 4.1 Create `src/obsidian_ops/anchors.py`

```python
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


def ensure_block_id_in_text(text: str, line_start: int, line_end: int) -> tuple[str, bool, str, int]:
    lines = text.splitlines(keepends=True)
    line_start, line_end = _normalize_range(line_start, line_end, len(lines))

    existing = _extract_existing_anchor(lines, line_start, line_end)
    if existing is not None:
        return existing, False, text, line_end

    target_idx = _choose_anchor_line(lines, line_start, line_end)
    block_id = f"forge-{secrets.token_hex(3)}"
    lines[target_idx] = _append_anchor(lines[target_idx], block_id)

    updated = "".join(lines)
    return block_id, True, updated, target_idx + 1


def ensure_block_result(path: str, text: str, line_start: int, line_end: int) -> tuple[EnsureBlockResult, str]:
    block_id, created, updated_text, anchor_line = ensure_block_id_in_text(text, line_start, line_end)
    final_text = updated_text if created else text

    result = EnsureBlockResult(
        path=path,
        block_id=block_id,
        created=created,
        line_start=line_start,
        line_end=anchor_line,
        sha256=_sha256(final_text),
    )
    return result, final_text
```

### 4.2 Add `Vault.ensure_block_id`

Update `src/obsidian_ops/vault.py` imports:

```python
from obsidian_ops.anchors import EnsureBlockResult, ensure_block_result
```

Add method:

```python
def ensure_block_id(self, path: str, line_start: int, line_end: int) -> EnsureBlockResult:
    with self._lock:
        text = self.read_file(path)
        result, final_text = ensure_block_result(path, text, line_start, line_end)

        if result.created:
            self._unsafe_write_file(path, final_text)

        return result
```

Update exports in `src/obsidian_ops/__init__.py`:

```python
from obsidian_ops.anchors import EnsureBlockResult

__all__ = [
    # existing exports...
    "EnsureBlockResult",
]
```

### 4.3 Add tests (`tests/test_anchors.py`)

```python
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from obsidian_ops.errors import BusyError, PathError
from obsidian_ops.vault import Vault


@pytest.fixture
def anchor_vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "note.md").write_text("# Note\n\nLine one\nLine two\n", encoding="utf-8")
    return root


def test_existing_anchor_returns_created_false(anchor_vault: Path) -> None:
    path = anchor_vault / "note.md"
    path.write_text("# Note\n\nParagraph line ^existing\n", encoding="utf-8")

    result = Vault(anchor_vault).ensure_block_id("note.md", 3, 3)

    assert result.created is False
    assert result.block_id == "existing"


def test_new_anchor_is_written(anchor_vault: Path) -> None:
    vault = Vault(anchor_vault)

    result = vault.ensure_block_id("note.md", 3, 4)

    assert result.created is True
    updated = vault.read_file("note.md")
    assert f"^{result.block_id}" in updated


def test_concurrent_ensure_converges_on_single_anchor(anchor_vault: Path) -> None:
    vault = Vault(anchor_vault)

    def ensure_with_retry() -> str:
        for _ in range(50):
            try:
                return vault.ensure_block_id("note.md", 3, 4).block_id
            except BusyError:
                time.sleep(0.01)
        raise AssertionError("failed to acquire mutation lock")

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _i: ensure_with_retry(), [0, 1]))

    assert ids[0] == ids[1]
    assert vault.read_file("note.md").count(f"^{ids[0]}") == 1


def test_ensure_block_id_rejects_escape(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    with pytest.raises(PathError):
        vault.ensure_block_id("../secret.md", 1, 1)
```

### 4.4 Phase 0.2 gate

```bash
devenv shell -- pytest tests/test_anchors.py -v
devenv shell -- pytest tests/test_content.py tests/test_vault.py -q
```

## 5) Phase 0.3: Vault-Local Templates and Deterministic Page Creation

### 5.1 Create `src/obsidian_ops/templates.py`

```python
"""Vault-local template loading and deterministic rendering."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from obsidian_ops.errors import VaultError
from obsidian_ops.sandbox import validate_path

_EXPR_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")
_SLUG_CALL_RE = re.compile(r"^slug\(([A-Za-z_][A-Za-z0-9_]*)\)$")
_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class TemplateField:
    name: str
    label: str
    required: bool = True
    description: str | None = None
    default: str | None = None


@dataclass(frozen=True)
class TemplateDefinition:
    key: str
    label: str
    path_template: str
    body_template: str
    fields: tuple[TemplateField, ...]
    commit_message: str | None = None


@dataclass(frozen=True)
class CreatePageResult:
    template_id: str
    path: str
    sha256: str


def _slug(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    return lowered or "untitled"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _template_dir(vault_root: Path) -> Path:
    return vault_root / ".forge" / "templates"


def _parse_field(raw: dict[str, Any]) -> TemplateField:
    name = str(raw.get("name", "")).strip()
    if not _FIELD_NAME_RE.match(name):
        raise VaultError(f"invalid template field name: {name!r}")

    label = str(raw.get("label") or name)
    required = bool(raw.get("required", True))
    description = raw.get("description")
    default = raw.get("default")

    return TemplateField(
        name=name,
        label=label,
        required=required,
        description=str(description) if description is not None else None,
        default=str(default) if default is not None else None,
    )


def _parse_template(path: Path) -> TemplateDefinition:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise VaultError(f"template {path.name} must be a mapping")

    key = str(raw.get("id", "")).strip()
    label = str(raw.get("label") or key)
    path_template = str(raw.get("path", "")).strip()
    body_template = str(raw.get("body", ""))

    if not key:
        raise VaultError(f"template {path.name} missing required field: id")
    if not path_template:
        raise VaultError(f"template {path.name} missing required field: path")

    raw_fields = raw.get("fields", [])
    if not isinstance(raw_fields, list):
        raise VaultError(f"template {path.name} field 'fields' must be a list")

    fields = tuple(_parse_field(item) for item in raw_fields)
    commit_message = raw.get("commit_message")

    return TemplateDefinition(
        key=key,
        label=label,
        path_template=path_template,
        body_template=body_template,
        fields=fields,
        commit_message=str(commit_message) if commit_message else None,
    )


def list_templates(vault_root: Path) -> list[TemplateDefinition]:
    template_dir = _template_dir(vault_root)
    if not template_dir.exists():
        return []

    templates: list[TemplateDefinition] = []
    for template_path in sorted(template_dir.glob("*.yaml")):
        templates.append(_parse_template(template_path))
    return templates


def _build_context(template: TemplateDefinition, provided: dict[str, str]) -> dict[str, str]:
    ctx: dict[str, str] = {}

    for field in template.fields:
        value = provided.get(field.name)
        if (value is None or value == "") and field.default is not None:
            value = field.default

        if field.required and (value is None or value == ""):
            raise VaultError(f"missing required template field: {field.name}")

        if value is not None:
            ctx[field.name] = str(value)

    return ctx


def _eval_expr(expr: str, ctx: dict[str, str], now: datetime) -> str:
    expr = expr.strip()

    if expr == "today":
        return now.date().isoformat()
    if expr == "now":
        return now.replace(microsecond=0).isoformat()

    slug_match = _SLUG_CALL_RE.match(expr)
    if slug_match is not None:
        name = slug_match.group(1)
        if name not in ctx:
            raise VaultError(f"unknown field for slug(): {name}")
        return _slug(ctx[name])

    if _FIELD_NAME_RE.match(expr):
        if expr not in ctx:
            raise VaultError(f"unknown field: {expr}")
        return ctx[expr]

    raise VaultError(f"unsupported template expression: {expr}")


def _render(text: str, ctx: dict[str, str], now: datetime) -> str:
    return _EXPR_RE.sub(lambda m: _eval_expr(m.group(1), ctx, now), text)


def render_template(
    vault_root: Path,
    template: TemplateDefinition,
    fields: dict[str, str],
    *,
    now: datetime | None = None,
) -> tuple[str, str]:
    render_now = now or datetime.now(UTC)
    ctx = _build_context(template, fields)

    rendered_path = _render(template.path_template, ctx, render_now)
    rendered_body = _render(template.body_template, ctx, render_now)

    safe_path = validate_path(vault_root, rendered_path)
    rel = safe_path.relative_to(vault_root).as_posix()
    return rel, rendered_body


def create_from_template(
    vault_root: Path,
    templates: list[TemplateDefinition],
    template_id: str,
    fields: dict[str, str],
    *,
    now: datetime | None = None,
) -> tuple[CreatePageResult, str, str]:
    template = next((item for item in templates if item.key == template_id), None)
    if template is None:
        raise VaultError(f"unknown template id: {template_id}")

    path, body = render_template(vault_root, template, fields, now=now)
    abs_path = validate_path(vault_root, path)
    if abs_path.exists():
        raise FileExistsError(path)

    if body and not body.endswith("\n"):
        body += "\n"

    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(body, encoding="utf-8")

    result = CreatePageResult(template_id=template_id, path=path, sha256=_sha256(body))

    commit_message = template.commit_message or f"ops: create {template_id} page {path}"
    return result, body, commit_message
```

### 5.2 Add template APIs to `Vault`

Update imports in `src/obsidian_ops/vault.py`:

```python
from obsidian_ops.templates import (
    CreatePageResult,
    TemplateDefinition,
    create_from_template,
    list_templates,
)
```

Add methods:

```python
def list_templates(self) -> list[TemplateDefinition]:
    return list_templates(self.root)


def create_from_template(self, template_id: str, fields: dict[str, str]) -> CreatePageResult:
    with self._lock:
        templates = list_templates(self.root)
        result, _body, commit_message = create_from_template(
            self.root,
            templates,
            template_id,
            fields,
        )

        # Commit inside the same critical section as file creation.
        jj = self._get_jj()
        jj.describe(commit_message)
        jj.new()

        return result
```

Important: do **not** call `self.commit()` inside the lock. `self.commit()` also
acquires the lock, and `MutationLock` is non-reentrant.

### 5.3 Export template models

Update `src/obsidian_ops/__init__.py`:

```python
from obsidian_ops.templates import CreatePageResult, TemplateDefinition, TemplateField

__all__ = [
    # existing exports...
    "TemplateField",
    "TemplateDefinition",
    "CreatePageResult",
]
```

### 5.4 Add tests (`tests/test_templates.py`)

```python
from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_ops.errors import PathError, VaultError
from obsidian_ops.vault import Vault


@pytest.fixture
def template_vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    root.mkdir()

    template_dir = root / ".forge" / "templates"
    template_dir.mkdir(parents=True)

    (template_dir / "project.yaml").write_text(
        """
id: project
label: Project
path: "Projects/{{ slug(title) }}.md"
fields:
  - name: title
    label: Title
    required: true
body: |
  ---
  type: project
  created: {{ today }}
  ---

  # {{ title }}

  ## Goal

  ## Notes
""".strip()
        + "\n",
        encoding="utf-8",
    )

    return root


def test_list_templates_discovers_yaml_specs(template_vault: Path) -> None:
    templates = Vault(template_vault).list_templates()
    assert [t.key for t in templates] == ["project"]
    assert templates[0].fields[0].name == "title"


def test_create_from_template_renders_path_and_body(template_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class StubJJ:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def describe(self, message: str) -> None:
            self.calls.append(("describe", message))

        def new(self) -> None:
            self.calls.append(("new", None))

    stub = StubJJ()
    vault = Vault(template_vault)
    monkeypatch.setattr(vault, "_get_jj", lambda: stub)

    result = vault.create_from_template("project", {"title": "Website Refresh"})

    assert result.path == "Projects/website-refresh.md"
    created = (template_vault / result.path).read_text(encoding="utf-8")
    assert "# Website Refresh" in created
    assert stub.calls[0][0] == "describe"
    assert stub.calls[1][0] == "new"


def test_create_from_template_missing_required_field_fails(template_vault: Path) -> None:
    vault = Vault(template_vault)
    with pytest.raises(VaultError, match="missing required template field"):
        vault.create_from_template("project", {})


def test_create_from_template_duplicate_path_fails(template_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = template_vault / "Projects" / "website-refresh.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("existing\n", encoding="utf-8")

    class StubJJ:
        def describe(self, _message: str) -> None:
            raise AssertionError("jj.describe should not be called on duplicate path")

        def new(self) -> None:
            raise AssertionError("jj.new should not be called on duplicate path")

    vault = Vault(template_vault)
    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())

    with pytest.raises(FileExistsError):
        vault.create_from_template("project", {"title": "Website Refresh"})


def test_template_path_escape_fails(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()

    template_dir = root / ".forge" / "templates"
    template_dir.mkdir(parents=True)
    (template_dir / "bad.yaml").write_text(
        """
id: bad
label: Bad
path: "../outside/{{ title }}.md"
fields:
  - name: title
    required: true
body: "x"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    vault = Vault(root)
    with pytest.raises(PathError):
        vault.create_from_template("bad", {"title": "oops"})
```

### 5.5 Phase 0.3 gate

```bash
devenv shell -- pytest tests/test_templates.py -v
devenv shell -- pytest tests/test_vcs.py tests/test_vault.py -q
```

## 6) Phase 0.4: Integration and Export Wiring

### 6.1 Consolidated `Vault` surface after this phase

At completion, `Vault` should expose these additional primitives:

```python
list_structure(path: str) -> StructureView
ensure_block_id(path: str, line_start: int, line_end: int) -> EnsureBlockResult
list_templates() -> list[TemplateDefinition]
create_from_template(template_id: str, fields: dict[str, str]) -> CreatePageResult
```

### 6.2 Update package exports in `src/obsidian_ops/__init__.py`

The expanded `__all__` should include all new models so route layers can import
them from package root:

```python
"Heading",
"Block",
"StructureView",
"EnsureBlockResult",
"TemplateField",
"TemplateDefinition",
"CreatePageResult",
```

### 6.3 Keep module boundaries strict

- `structure.py`: pure parsing + immutable output models.
- `anchors.py`: pure anchor-ensuring logic + result model.
- `templates.py`: registry + rendering + create helper.
- `vault.py`: orchestration, lock handling, JJ interaction.

No module besides `vault.py` should call JJ.

## 7) Test Plan by Phase

1. Structure tests (`tests/test_structure.py`)
   - heading-range determinism with mixed levels.
   - multiline paragraph block span derivation.
   - empty-file shape and hash.
   - path sandbox escape rejection via `Vault.list_structure()`.
2. Anchor tests (`tests/test_anchors.py`)
   - idempotent reuse of existing `^id`.
   - new anchor generation + persisted write.
   - lock contention convergence (retry on `BusyError`).
   - path sandbox escape rejection.
3. Template tests (`tests/test_templates.py`)
   - template discovery from `.forge/templates/*.yaml`.
   - required field validation.
   - deterministic rendering for `today`, `now`, `slug(field)`, `field`.
   - duplicate path failure.
   - escape path failure through sandbox validation.
   - JJ commit side-effects on success.

## 8) Final Validation Gate

Run the complete verification matrix in this order:

```bash
devenv shell -- uv sync --extra dev
devenv shell -- pytest tests/test_structure.py tests/test_anchors.py tests/test_templates.py -v
devenv shell -- pytest tests -v
devenv shell -- pytest --cov=obsidian_ops --cov-fail-under=90
devenv shell -- ruff check src tests
```

Optional type-check gate if `mypy` is present in the development shell:

```bash
devenv shell -- mypy src/obsidian_ops
```

## 9) Hand-off Checklist for obsidian-agent

Before starting obsidian-agent route work, verify all items are true:

1. `Vault.list_structure` returns deterministic hash + line-ranged headings and
   block anchors.
2. `Vault.ensure_block_id` is idempotent and safe under mutation locking.
3. `Vault.list_templates` returns parseable template metadata.
4. `Vault.create_from_template` performs sandboxed create + JJ commit in one
   locked critical section.
5. New model types are exported from `obsidian_ops.__init__`.
6. New tests are green and included in normal test runs.

When these are done, downstream route wiring can be implemented in
`OBSIDIAN_AGENT_EXPANSION_IMPLEMENTATION_GUIDE.md` with thin wrappers only.
