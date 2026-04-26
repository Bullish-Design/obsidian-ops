from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsidian_ops.errors import (
    BusyError,
    ContentPatchError,
    FileTooLargeError,
    FrontmatterError,
    PathError,
    VCSError,
)
from obsidian_ops.server import create_app
from obsidian_ops.vcs import ReadinessCheck, SyncResult, UndoResult, VCSReadiness


@pytest.fixture
def client(tmp_vault: Path) -> TestClient:
    app = create_app(str(tmp_vault))
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "status": "healthy"}


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


def test_set_frontmatter(client: TestClient) -> None:
    response = client.put("/frontmatter/note.md", json={"title": "Replaced"})
    assert response.status_code == 200

    check = client.get("/frontmatter/note.md")
    fm = check.json()["frontmatter"]
    assert fm["title"] == "Replaced"
    assert "tags" not in fm


def test_delete_frontmatter_field(client: TestClient) -> None:
    response = client.delete("/frontmatter/note.md/status")
    assert response.status_code == 200

    check = client.get("/frontmatter/note.md")
    assert "status" not in check.json()["frontmatter"]


def test_read_heading(client: TestClient) -> None:
    response = client.post("/content/heading/note.md/read", json={"heading": "## Summary"})
    assert response.status_code == 200
    assert response.json()["content"] is not None


def test_write_heading(client: TestClient) -> None:
    response = client.put("/content/heading/note.md", json={"heading": "## Summary", "content": "New summary.\n"})
    assert response.status_code == 200

    check = client.post("/content/heading/note.md/read", json={"heading": "## Summary"})
    assert "New summary." in check.json()["content"]


def test_read_block(client: TestClient) -> None:
    response = client.post("/content/block/note.md/read", json={"block_id": "^ref-block"})
    assert response.status_code == 200
    assert response.json()["content"] is not None


def test_write_block(client: TestClient) -> None:
    response = client.put("/content/block/note.md", json={"block_id": "^ref-block", "content": "Updated ^ref-block\n"})
    assert response.status_code == 200

    check = client.post("/content/block/note.md/read", json={"block_id": "^ref-block"})
    assert "Updated" in check.json()["content"]


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


def test_file_too_large_returns_413(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "read_file", lambda _path: (_ for _ in ()).throw(FileTooLargeError("too big")))

    response = client.get("/files/note.md")
    assert response.status_code == 413


def test_frontmatter_error_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "get_frontmatter", lambda _path: (_ for _ in ()).throw(FrontmatterError("bad yaml")))

    response = client.get("/frontmatter/note.md")
    assert response.status_code == 422


def test_content_patch_error_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "write_block", lambda *_args: (_ for _ in ()).throw(ContentPatchError("not found")))

    response = client.put("/content/block/note.md", json={"block_id": "^x", "content": "y"})
    assert response.status_code == 422


def test_vcs_commit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    messages: list[str] = []

    def fake_commit(message: str) -> None:
        messages.append(message)

    monkeypatch.setattr(vault, "commit", fake_commit)
    response = client.post("/vcs/commit", json={"message": "hello"})

    assert response.status_code == 200
    assert messages == ["hello"]


def test_vcs_status(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "vcs_status", lambda: "Working copy changes:\nM note.md\n")

    response = client.get("/vcs/status")
    assert response.status_code == 200
    assert "note.md" in response.json()["status"]


def test_vcs_undo(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    called: list[bool] = []
    monkeypatch.setattr(vault, "undo_last_change", lambda: (called.append(True), UndoResult(restored=True))[1])

    response = client.post("/vcs/undo")
    assert response.status_code == 200
    assert called
    assert response.json() == {"status": "ok", "restored": True, "warning": None}


def test_vcs_undo_warning_response(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "undo_last_change", lambda: UndoResult(restored=False, warning="restore failed"))

    response = client.post("/vcs/undo")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "restored": False, "warning": "restore failed"}


def test_vcs_error_precondition_returns_424(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "commit", lambda _message: (_ for _ in ()).throw(VCSError("jj binary not found")))

    response = client.post("/vcs/commit", json={"message": "x"})
    assert response.status_code == 424


def test_vcs_error_execution_returns_500(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    monkeypatch.setattr(
        vault,
        "commit",
        lambda _message: (_ for _ in ()).throw(VCSError("jj command failed: merge conflict")),
    )

    response = client.post("/vcs/commit", json={"message": "x"})
    assert response.status_code == 500


def test_write_file_validation_error_returns_422(client: TestClient) -> None:
    response = client.put("/files/note.md", json={"body": "missing content"})
    assert response.status_code == 422


def test_write_heading_validation_error_returns_422(client: TestClient) -> None:
    response = client.put("/content/heading/note.md", json={"heading": "## Summary"})
    assert response.status_code == 422


def test_vcs_sync_readiness(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "check_sync_readiness", lambda: ReadinessCheck(VCSReadiness.READY, None))
    response = client.get("/vcs/sync/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "detail": None}


def test_vcs_sync_ensure(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    monkeypatch.setattr(
        vault,
        "ensure_sync_ready",
        lambda: ReadinessCheck(VCSReadiness.MIGRATION_NEEDED, "git-only with uncommitted changes"),
    )
    response = client.post("/vcs/sync/ensure")
    assert response.status_code == 200
    assert response.json()["status"] == "migration_needed"


def test_vcs_sync_remote(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    seen: list[tuple[str, str | None, str]] = []

    def fake_configure(url: str, *, token: str | None = None, remote: str = "origin") -> None:
        seen.append((url, token, remote))

    monkeypatch.setattr(vault, "configure_sync_remote", fake_configure)
    response = client.put("/vcs/sync/remote", json={"url": "https://github.com/example/repo.git", "token": "x"})
    assert response.status_code == 200
    assert seen == [("https://github.com/example/repo.git", "x", "origin")]


def test_vcs_sync_fetch(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    seen: list[str] = []
    monkeypatch.setattr(vault, "sync_fetch", lambda *, remote="origin": seen.append(remote))
    response = client.post("/vcs/sync/fetch", json={"remote": "origin"})
    assert response.status_code == 200
    assert seen == ["origin"]


def test_vcs_sync_push(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    seen: list[str] = []
    monkeypatch.setattr(vault, "sync_push", lambda *, remote="origin": seen.append(remote))
    response = client.post("/vcs/sync/push", json={"remote": "origin"})
    assert response.status_code == 200
    assert seen == ["origin"]


def test_vcs_sync(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    monkeypatch.setattr(
        vault,
        "sync",
        lambda *, remote="origin", conflict_prefix="sync-conflict": SyncResult(ok=True),
    )
    response = client.post("/vcs/sync", json={})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "conflict": False, "conflict_bookmark": None, "error": None}


def test_vcs_sync_status(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = client.app.state.vault
    monkeypatch.setattr(
        vault,
        "sync_status",
        lambda: {
            "last_sync_at": "2026-04-26T12:34:56+00:00",
            "last_sync_ok": True,
            "conflict_active": False,
            "conflict_bookmark": None,
        },
    )
    response = client.get("/vcs/sync/status")
    assert response.status_code == 200
    assert response.json()["last_sync_ok"] is True
