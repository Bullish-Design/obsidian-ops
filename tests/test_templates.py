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
    assert [template.key for template in templates] == ["project"]
    assert templates[0].fields[0].name == "title"


def test_create_from_template_renders_path_and_body(
    template_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_create_from_template_duplicate_path_fails(
    template_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_template_path_escape_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    class StubJJ:
        def describe(self, _message: str) -> None:
            raise AssertionError("jj.describe should not be called on unsafe path")

        def new(self) -> None:
            raise AssertionError("jj.new should not be called on unsafe path")

    vault = Vault(root)
    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    with pytest.raises(PathError):
        vault.create_from_template("bad", {"title": "oops"})
