"""Optional FastAPI server for obsidian-ops."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

SERVER_INSTALL_HINT = "Install server support with: pip install \"obsidian-ops[server]\""

from obsidian_ops.errors import BusyError, ContentPatchError, FileTooLargeError, FrontmatterError, PathError, VCSError
from obsidian_ops.vault import Vault


def _load_fastapi_runtime() -> tuple[Any, type[FastAPI], type[JSONResponse]]:
    try:
        from fastapi import Body, FastAPI
        from fastapi.responses import JSONResponse
    except ModuleNotFoundError as exc:
        if exc.name != "fastapi":
            raise
        raise RuntimeError(f"FastAPI server support is not installed. {SERVER_INSTALL_HINT}") from exc
    return Body, FastAPI, JSONResponse


def _load_uvicorn_runtime() -> Any:
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        if exc.name != "uvicorn":
            raise
        raise RuntimeError(f"Uvicorn server support is not installed. {SERVER_INSTALL_HINT}") from exc
    return uvicorn


def _status_for_vcs_error(exc: VCSError) -> int:
    message = str(exc).lower()
    if "not found" in message or "workspace" in message:
        return 424
    return 500


def create_app(vault_root: str, *, jj_bin: str = "jj", jj_timeout: int = 120) -> FastAPI:
    Body, FastAPI, JSONResponse = _load_fastapi_runtime()
    body_str_map = Body(...)
    body_any_map = Body(...)
    app = FastAPI(title="obsidian-ops")
    app.state.vault = Vault(vault_root, jj_bin=jj_bin, jj_timeout=jj_timeout)

    @app.exception_handler(PathError)
    async def handle_path_error(_request: Any, exc: PathError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(FileNotFoundError)
    async def handle_not_found(_request: Any, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": str(exc)})

    @app.exception_handler(FileTooLargeError)
    async def handle_too_large(_request: Any, exc: FileTooLargeError) -> JSONResponse:
        return JSONResponse(status_code=413, content={"error": str(exc)})

    @app.exception_handler(BusyError)
    async def handle_busy(_request: Any, exc: BusyError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": str(exc)})

    @app.exception_handler(FrontmatterError)
    async def handle_frontmatter(_request: Any, exc: FrontmatterError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": str(exc)})

    @app.exception_handler(ContentPatchError)
    async def handle_content_patch(_request: Any, exc: ContentPatchError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": str(exc)})

    @app.exception_handler(VCSError)
    async def handle_vcs(_request: Any, exc: VCSError) -> JSONResponse:
        return JSONResponse(status_code=_status_for_vcs_error(exc), content={"error": str(exc)})

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/files/{path:path}")
    async def read_file(path: str) -> dict[str, str]:
        return {"content": app.state.vault.read_file(path)}

    @app.put("/files/{path:path}")
    async def write_file(path: str, payload: dict[str, str] = body_str_map) -> dict[str, str]:
        app.state.vault.write_file(path, payload["content"])
        return {"status": "ok"}

    @app.delete("/files/{path:path}")
    async def delete_file(path: str) -> dict[str, str]:
        app.state.vault.delete_file(path)
        return {"status": "ok"}

    @app.get("/files")
    async def list_files(pattern: str = "*.md", max_results: int = 200) -> dict[str, list[str]]:
        return {"files": app.state.vault.list_files(pattern, max_results=max_results)}

    @app.get("/search")
    async def search(query: str, glob: str = "*.md", max_results: int = 50) -> dict[str, list[dict[str, str]]]:
        results = app.state.vault.search_files(query, glob=glob, max_results=max_results)
        return {"results": [{"path": r.path, "snippet": r.snippet} for r in results]}

    @app.get("/frontmatter/{path:path}")
    async def get_frontmatter(path: str) -> dict[str, Any]:
        return {"frontmatter": app.state.vault.get_frontmatter(path)}

    @app.put("/frontmatter/{path:path}")
    async def set_frontmatter(path: str, payload: dict[str, Any] = body_any_map) -> dict[str, str]:
        app.state.vault.set_frontmatter(path, payload)
        return {"status": "ok"}

    @app.patch("/frontmatter/{path:path}")
    async def update_frontmatter(path: str, payload: dict[str, Any] = body_any_map) -> dict[str, str]:
        app.state.vault.update_frontmatter(path, payload)
        return {"status": "ok"}

    @app.delete("/frontmatter/{path:path}/{field}")
    async def delete_frontmatter_field(path: str, field: str) -> dict[str, str]:
        app.state.vault.delete_frontmatter_field(path, field)
        return {"status": "ok"}

    @app.post("/content/heading/{path:path}/read")
    async def read_heading(path: str, payload: dict[str, str] = body_str_map) -> dict[str, Any]:
        return {"content": app.state.vault.read_heading(path, payload["heading"])}

    @app.put("/content/heading/{path:path}")
    async def write_heading(path: str, payload: dict[str, str] = body_str_map) -> dict[str, str]:
        app.state.vault.write_heading(path, payload["heading"], payload["content"])
        return {"status": "ok"}

    @app.post("/content/block/{path:path}/read")
    async def read_block(path: str, payload: dict[str, str] = body_str_map) -> dict[str, Any]:
        return {"content": app.state.vault.read_block(path, payload["block_id"])}

    @app.put("/content/block/{path:path}")
    async def write_block(path: str, payload: dict[str, str] = body_str_map) -> dict[str, str]:
        app.state.vault.write_block(path, payload["block_id"], payload["content"])
        return {"status": "ok"}

    @app.post("/vcs/commit")
    async def commit(payload: dict[str, str] = body_str_map) -> dict[str, str]:
        app.state.vault.commit(payload["message"])
        return {"status": "ok"}

    @app.post("/vcs/undo")
    async def undo() -> dict[str, str]:
        app.state.vault.undo()
        return {"status": "ok"}

    @app.get("/vcs/status")
    async def status() -> dict[str, str]:
        return {"status": app.state.vault.vcs_status()}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the obsidian-ops HTTP server")
    parser.add_argument("--vault", required=True, help="Vault root directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9200)
    parser.add_argument("--jj-bin", default="jj")
    parser.add_argument("--jj-timeout", type=int, default=120)
    args = parser.parse_args()

    app = create_app(args.vault, jj_bin=args.jj_bin, jj_timeout=args.jj_timeout)
    uvicorn = _load_uvicorn_runtime()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
