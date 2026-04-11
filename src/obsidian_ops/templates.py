"""Vault-local template loading and deterministic rendering."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
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


def template_dir(vault_root: Path) -> Path:
    custom_dir = os.environ.get("AGENT_TEMPLATE_DIR")
    if custom_dir:
        return Path(custom_dir)
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
    registry = template_dir(vault_root)
    if not registry.exists():
        return []

    templates: list[TemplateDefinition] = []
    for template_path in sorted(registry.glob("*.yaml")):
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
    return _EXPR_RE.sub(lambda match: _eval_expr(match.group(1), ctx, now), text)


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

    sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    result = CreatePageResult(template_id=template_id, path=path, sha256=sha256)
    commit_message = template.commit_message or f"ops: create {template_id} page {path}"
    return result, body, commit_message
