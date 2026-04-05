from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import typer

from obsidian_ops import demo_cli


class DummyResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "http://example.invalid")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad status", request=self.request, response=httpx.Response(self.status_code))

    def json(self) -> dict:
        return self._payload


def test_normalize_vllm_base_url_appends_v1() -> None:
    assert demo_cli._normalize_vllm_base_url("http://remora-server:8000") == "http://remora-server:8000/v1"


def test_normalize_vllm_base_url_keeps_v1() -> None:
    assert demo_cli._normalize_vllm_base_url("http://remora-server:8000/v1/") == "http://remora-server:8000/v1"


def test_normalize_vllm_base_url_rejects_empty() -> None:
    with pytest.raises(typer.Exit):
        demo_cli._normalize_vllm_base_url("")


def test_fetch_vllm_models_parses_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        demo_cli.httpx,
        "get",
        lambda *_args, **_kwargs: DummyResponse({"data": [{"id": "model-a"}, {"id": "model-b"}]}),
    )

    models = demo_cli._fetch_vllm_models("http://remora-server:8000/v1")
    assert models == ["model-a", "model-b"]


def test_resolve_vllm_model_auto_selects_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo_cli, "_fetch_vllm_models", lambda _base_url: ["model-a", "model-b"])

    selected = demo_cli._resolve_vllm_model("http://remora-server:8000/v1", "")
    assert selected == "model-a"


def test_resolve_vllm_model_validates_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo_cli, "_fetch_vllm_models", lambda _base_url: ["model-a", "model-b"])

    assert demo_cli._resolve_vllm_model("http://remora-server:8000/v1", "model-b") == "model-b"

    with pytest.raises(typer.Exit):
        demo_cli._resolve_vllm_model("http://remora-server:8000/v1", "missing-model")


def test_run_server_sets_vllm_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict = {}

    def fake_run_command(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env or {}

    monkeypatch.setattr(demo_cli, "_run_command", fake_run_command)
    monkeypatch.setattr(demo_cli, "_normalize_vllm_base_url", lambda _url: "http://remora-server:8000/v1")
    monkeypatch.setattr(demo_cli, "_resolve_vllm_model", lambda _base_url, _requested: "resolved-model")

    paths = demo_cli.DemoPaths(
        repo_root=tmp_path,
        demo_root=tmp_path / "demo",
        source_vault=tmp_path / "vault-source",
        gen_root=tmp_path / "gen",
        site_root=tmp_path / "gen" / "site",
        work_root=tmp_path / "work",
        runtime_vault=tmp_path / "runtime-vault",
    )
    paths.runtime_vault.mkdir(parents=True)

    demo_cli._run_server(
        paths=paths,
        host="127.0.0.1",
        port=8080,
        vllm_base_url="http://remora-server:8000",
        vllm_model="",
        vllm_api_key="EMPTY",
    )

    env = captured["env"]
    assert captured["command"] == ["uvicorn", "obsidian_ops.app:app", "--host", "127.0.0.1", "--port", "8080"]
    assert captured["cwd"] == tmp_path
    assert env["OPS_VAULT_DIR"] == str(paths.runtime_vault)
    assert env["OPS_SITE_DIR"] == str(paths.site_root)
    assert env["OPS_VLLM_BASE_URL"] == "http://remora-server:8000/v1"
    assert env["OPS_VLLM_MODEL"] == "resolved-model"
    assert env["OPS_VLLM_API_KEY"] == "EMPTY"
