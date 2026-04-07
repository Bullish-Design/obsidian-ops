from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsidian_ops.errors import BusyError, PathError
from obsidian_ops.server import create_app


@pytest.fixture
def client(tmp_vault: Path) -> TestClient:
    app = create_app(str(tmp_vault))
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_read_file(client: TestClient) -> None:
    response = client.get("/files/note.md")
    assert response.status_code == 200
    assert "# Test Note" in response.json()["content"]


def test_read_file_not_found(client: TestClient) -> None:
    response = client.get("/files/missing.md")
    assert response.status_code == 404
    assert "error" in response.json()


def test_write_file(client: TestClient) -> None:
    response = client.put("/files/new.md", json={"content": "hello"})
    assert response.status_code == 200

    read_back = client.get("/files/new.md")
    assert read_back.json()["content"] == "hello"


def test_delete_file(client: TestClient) -> None:
    response = client.delete("/files/no-frontmatter.md")
    assert response.status_code == 200

    missing = client.get("/files/no-frontmatter.md")
    assert missing.status_code == 404


def test_list_files(client: TestClient) -> None:
    response = client.get("/files", params={"pattern": "*.md"})
    assert response.status_code == 200
    assert "note.md" in response.json()["files"]


def test_search_files(client: TestClient) -> None:
    response = client.get("/search", params={"query": "summary"})
    assert response.status_code == 200
    assert any(r["path"] == "note.md" for r in response.json()["results"])


def test_get_frontmatter(client: TestClient) -> None:
    response = client.get("/frontmatter/note.md")
    assert response.status_code == 200
    assert response.json()["frontmatter"]["title"] == "Test Note"


def test_update_frontmatter(client: TestClient) -> None:
    response = client.patch("/frontmatter/note.md", json={"status": "published"})
    assert response.status_code == 200

    check = client.get("/frontmatter/note.md")
    assert check.json()["frontmatter"]["status"] == "published"


def test_path_error_returns_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault

    def boom(_path: str) -> str:
        raise PathError("bad path")

    monkeypatch.setattr(vault, "read_file", boom)
    response = client.get("/files/note.md")
    assert response.status_code == 400


def test_busy_returns_409(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault

    def boom(_path: str, _content: str) -> None:
        raise BusyError("busy")

    monkeypatch.setattr(vault, "write_file", boom)
    response = client.put("/files/note.md", json={"content": "x"})
    assert response.status_code == 409


def test_vcs_commit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    messages: list[str] = []

    def fake_commit(message: str) -> None:
        messages.append(message)

    monkeypatch.setattr(vault, "commit", fake_commit)
    response = client.post("/vcs/commit", json={"message": "hello"})

    assert response.status_code == 200
    assert messages == ["hello"]
