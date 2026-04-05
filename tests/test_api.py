from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsidian_ops.config import get_settings


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    vault_dir = tmp_path / "vault"
    site_dir = tmp_path / "site"
    vault_dir.mkdir()
    site_dir.mkdir()

    (vault_dir / "index.md").write_text("home", encoding="utf-8")
    (site_dir / "index.html").write_text("<html><head></head><body>ok</body></html>", encoding="utf-8")
    (site_dir / "guides").mkdir()
    (site_dir / "guides" / "getting-started.html").write_text(
        "<html><head></head><body>getting started</body></html>",
        encoding="utf-8",
    )
    (site_dir / "docs" / "page").mkdir(parents=True)
    (site_dir / "docs" / "page" / "index.html").write_text(
        "<html><head></head><body>docs page</body></html>",
        encoding="utf-8",
    )

    monkeypatch.setenv("OPS_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("OPS_SITE_DIR", str(site_dir))

    get_settings.cache_clear()

    import obsidian_ops.app as app_module

    app_module = importlib.reload(app_module)

    async def fake_ensure_workspace(self) -> None:  # noqa: ANN001
        return None

    async def fake_rebuild(self) -> str:  # noqa: ANN001
        return "ok"

    async def fake_run_worker(*_args, **_kwargs) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(app_module.JujutsuHistory, "ensure_workspace", fake_ensure_workspace)
    monkeypatch.setattr(app_module.KilnRebuilder, "rebuild", fake_rebuild)
    monkeypatch.setattr(app_module, "run_worker", fake_run_worker)

    with TestClient(app_module.app) as client:
        yield client


def test_health_endpoint(test_client: TestClient) -> None:
    response = test_client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_job_returns_job_id(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/jobs",
        json={
            "instruction": "clean up this note",
            "current_url_path": "/",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "job_id" in payload
    assert isinstance(payload["job_id"], str)


def test_list_jobs_returns_array(test_client: TestClient) -> None:
    test_client.post(
        "/api/jobs",
        json={
            "instruction": "clean up this note",
            "current_url_path": "/",
        },
    )

    response = test_client.get("/api/jobs")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_job_missing_instruction_returns_422(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/jobs",
        json={
            "current_url_path": "/",
        },
    )

    assert response.status_code == 422


def test_clean_url_rewrites_to_html_leaf_page(test_client: TestClient) -> None:
    response = test_client.get("/guides/getting-started")

    assert response.status_code == 200
    assert "getting started" in response.text


def test_clean_url_rewrites_to_directory_index(test_client: TestClient) -> None:
    response = test_client.get("/docs/page")

    assert response.status_code == 200
    assert "docs page" in response.text
