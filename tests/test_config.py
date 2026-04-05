from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from obsidian_ops.config import Settings


def test_required_fields_missing_raise_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPS_VAULT_DIR", raising=False)
    monkeypatch.delenv("OPS_SITE_DIR", raising=False)

    with pytest.raises(ValidationError):
        Settings()


def test_defaults_applied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    site_dir = tmp_path / "site"

    monkeypatch.setenv("OPS_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("OPS_SITE_DIR", str(site_dir))

    settings = Settings()
    assert settings.vault_dir == vault_dir.resolve()
    assert settings.site_dir == site_dir.resolve()
    assert settings.vllm_base_url == "http://127.0.0.1:8000/v1"
    assert settings.vllm_model == "local-model"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8080


def test_vault_dir_must_exist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing_vault = tmp_path / "missing"
    site_dir = tmp_path / "site"

    monkeypatch.setenv("OPS_VAULT_DIR", str(missing_vault))
    monkeypatch.setenv("OPS_SITE_DIR", str(site_dir))

    with pytest.raises(ValidationError):
        Settings()


def test_host_defaults_to_localhost(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    monkeypatch.setenv("OPS_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("OPS_SITE_DIR", str(tmp_path / "site"))
    monkeypatch.delenv("OPS_HOST", raising=False)

    settings = Settings()
    assert settings.host == "127.0.0.1"
