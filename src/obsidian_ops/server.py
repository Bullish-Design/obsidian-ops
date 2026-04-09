"""Optional FastAPI server for obsidian-ops."""

import argparse
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

SERVER_INSTALL_HINT = 'Install server support with: pip install "obsidian-ops[server]"'

from obsidian_ops.errors import BusyError, ContentPatchError, FileTooLargeError, FrontmatterError, PathError, VCSError
from obsidian_ops.vault import Vault


def _load_fastapi_runtime() -> tuple[type["FastAPI"], type["JSONResponse"], type[Any], type[Any]]:
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel, RootModel
    except ModuleNotFoundError as exc:
        if exc.name not in {"fastapi", "pydantic"}:
            raise
        raise RuntimeError(f"FastAPI server support is not installed. {SERVER_INSTALL_HINT}") from exc
    return FastAPI, JSONResponse, BaseModel, RootModel


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


def create_app(vault_root: str, *, jj_bin: str = "jj", jj_timeout: int = 120) -> "FastAPI":
    FastAPI, JSONResponse, BaseModel, RootModel = _load_fastapi_runtime()

    class HealthResponse(BaseModel):
        ok: bool = True
        status: Literal["healthy"] = "healthy"

    class StatusResponse(BaseModel):
        status: Literal["ok"] = "ok"

    class UndoResponse(BaseModel):
        status: Literal["ok"] = "ok"
        restored: bool
        warning: str | None = None

    class FileContentResponse(BaseModel):
        content: str

    class OptionalContentResponse(BaseModel):
        content: str | None

    class FileListResponse(BaseModel):
        files: list[str]

    class SearchItem(BaseModel):
        path: str
        snippet: str

    class SearchResponse(BaseModel):
        results: list[SearchItem]

    class FrontmatterResponse(BaseModel):
        frontmatter: dict[str, Any] | None

    class VCSStatusResponse(BaseModel):
        status: str

    class FileWriteRequest(BaseModel):
        content: str

    class HeadingReadRequest(BaseModel):
        heading: str

    class HeadingWriteRequest(BaseModel):
        heading: str
        content: str

    class BlockReadRequest(BaseModel):
        block_id: str

    class BlockWriteRequest(BaseModel):
        block_id: str
        content: str

    class CommitRequest(BaseModel):
        message: str

    class FrontmatterPayload(RootModel[dict[str, Any]]):
        pass

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

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/files/{path:path}", response_model=FileContentResponse)
    async def read_file(path: str) -> FileContentResponse:
        return FileContentResponse(content=app.state.vault.read_file(path))

    @app.put("/files/{path:path}", response_model=StatusResponse)
    async def write_file(path: str, payload: FileWriteRequest) -> StatusResponse:
        app.state.vault.write_file(path, payload.content)
        return StatusResponse()

    @app.delete("/files/{path:path}", response_model=StatusResponse)
    async def delete_file(path: str) -> StatusResponse:
        app.state.vault.delete_file(path)
        return StatusResponse()

    @app.get("/files", response_model=FileListResponse)
    async def list_files(pattern: str = "*.md", max_results: int = 200) -> FileListResponse:
        return FileListResponse(files=app.state.vault.list_files(pattern, max_results=max_results))

    @app.get("/search", response_model=SearchResponse)
    async def search(query: str, glob: str = "*.md", max_results: int = 50) -> SearchResponse:
        results = app.state.vault.search_files(query, glob=glob, max_results=max_results)
        return SearchResponse(results=[SearchItem(path=result.path, snippet=result.snippet) for result in results])

    @app.get("/frontmatter/{path:path}", response_model=FrontmatterResponse)
    async def get_frontmatter(path: str) -> FrontmatterResponse:
        return FrontmatterResponse(frontmatter=app.state.vault.get_frontmatter(path))

    @app.put("/frontmatter/{path:path}", response_model=StatusResponse)
    async def set_frontmatter(path: str, payload: FrontmatterPayload) -> StatusResponse:
        app.state.vault.set_frontmatter(path, payload.root)
        return StatusResponse()

    @app.patch("/frontmatter/{path:path}", response_model=StatusResponse)
    async def update_frontmatter(path: str, payload: FrontmatterPayload) -> StatusResponse:
        app.state.vault.update_frontmatter(path, payload.root)
        return StatusResponse()

    @app.delete("/frontmatter/{path:path}/{field}", response_model=StatusResponse)
    async def delete_frontmatter_field(path: str, field: str) -> StatusResponse:
        app.state.vault.delete_frontmatter_field(path, field)
        return StatusResponse()

    @app.post("/content/heading/{path:path}/read", response_model=OptionalContentResponse)
    async def read_heading(path: str, payload: HeadingReadRequest) -> OptionalContentResponse:
        return OptionalContentResponse(content=app.state.vault.read_heading(path, payload.heading))

    @app.put("/content/heading/{path:path}", response_model=StatusResponse)
    async def write_heading(path: str, payload: HeadingWriteRequest) -> StatusResponse:
        app.state.vault.write_heading(path, payload.heading, payload.content)
        return StatusResponse()

    @app.post("/content/block/{path:path}/read", response_model=OptionalContentResponse)
    async def read_block(path: str, payload: BlockReadRequest) -> OptionalContentResponse:
        return OptionalContentResponse(content=app.state.vault.read_block(path, payload.block_id))

    @app.put("/content/block/{path:path}", response_model=StatusResponse)
    async def write_block(path: str, payload: BlockWriteRequest) -> StatusResponse:
        app.state.vault.write_block(path, payload.block_id, payload.content)
        return StatusResponse()

    @app.post("/vcs/commit", response_model=StatusResponse)
    async def commit(payload: CommitRequest) -> StatusResponse:
        app.state.vault.commit(payload.message)
        return StatusResponse()

    @app.post("/vcs/undo", response_model=UndoResponse)
    async def undo() -> UndoResponse:
        result = app.state.vault.undo_last_change()
        return UndoResponse(restored=result.restored, warning=result.warning)

    @app.get("/vcs/status", response_model=VCSStatusResponse)
    async def status() -> VCSStatusResponse:
        return VCSStatusResponse(status=app.state.vault.vcs_status())

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
