from __future__ import annotations

import json
from pathlib import Path

import httpx

from obsidian_ops.config import Settings
from obsidian_ops.fs_atomic import read_file_safe, validate_vault_path, write_file_atomic
from obsidian_ops.history_jj import JujutsuHistory
from obsidian_ops.locks import FileLockManager

FETCH_URL_LIMIT_BYTES = 120 * 1024


class ToolRuntime:
    def __init__(self, settings: Settings, lock_manager: FileLockManager, jj: JujutsuHistory) -> None:
        self._settings = settings
        self._locks = lock_manager
        self._jj = jj
        self.changed_files: list[str] = []

    def reset(self) -> None:
        self.changed_files = []

    async def read_file(self, path: str) -> str:
        abs_path = validate_vault_path(self._settings.vault_dir, Path(path))
        return read_file_safe(abs_path)

    async def write_file(self, path: str, content: str) -> str:
        abs_path = validate_vault_path(self._settings.vault_dir, Path(path))
        lock = self._locks.get_lock(str(abs_path))
        async with lock:
            write_file_atomic(abs_path, content)
        relative_path = abs_path.relative_to(self._settings.vault_dir).as_posix()
        if relative_path not in self.changed_files:
            self.changed_files.append(relative_path)
        return f"Wrote {relative_path} ({len(content.encode('utf-8'))} bytes)"

    async def list_files(self, glob_pattern: str = "**/*.md") -> list[str]:
        vault_dir = self._settings.vault_dir
        files = [
            path.relative_to(vault_dir).as_posix()
            for path in vault_dir.glob(glob_pattern)
            if path.is_file()
        ]
        return sorted(files)

    async def search_files(self, query: str, glob_pattern: str = "**/*.md") -> list[dict]:
        if not query:
            return []

        query_lower = query.lower()
        results: list[dict] = []
        for path in self._settings.vault_dir.glob(glob_pattern):
            if not path.is_file():
                continue

            content = read_file_safe(path)
            lines = content.splitlines()
            for idx, line in enumerate(lines):
                if query_lower not in line.lower():
                    continue

                start = max(0, idx - 1)
                end = min(len(lines), idx + 2)
                snippet = "\n".join(lines[start:end])
                results.append(
                    {
                        "path": path.relative_to(self._settings.vault_dir).as_posix(),
                        "snippet": snippet,
                    }
                )
                if len(results) >= self._settings.max_search_results:
                    return results
        return results

    async def fetch_url(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                text = response.text
                encoded = text.encode("utf-8")
                if len(encoded) > FETCH_URL_LIMIT_BYTES:
                    return encoded[:FETCH_URL_LIMIT_BYTES].decode("utf-8", errors="ignore")
                return text
        except Exception as exc:  # noqa: BLE001
            return f"Failed to fetch URL '{url}': {exc}"

    async def undo_last_change(self) -> str:
        return await self._jj.undo()

    async def get_file_history(self, path: str, limit: int = 10) -> list[str]:
        abs_path = validate_vault_path(self._settings.vault_dir, Path(path))
        relative_path = abs_path.relative_to(self._settings.vault_dir).as_posix()
        return await self._jj.log_for_file(relative_path, limit)

    async def call_tool(self, name: str, arguments: dict) -> str:
        try:
            if name == "read_file":
                return await self.read_file(arguments["path"])
            if name == "write_file":
                return await self.write_file(arguments["path"], arguments["content"])
            if name == "list_files":
                return json.dumps(await self.list_files(arguments.get("glob_pattern", "**/*.md")))
            if name == "search_files":
                return json.dumps(
                    await self.search_files(arguments["query"], arguments.get("glob_pattern", "**/*.md"))
                )
            if name == "fetch_url":
                return await self.fetch_url(arguments["url"])
            if name == "undo_last_change":
                return await self.undo_last_change()
            if name == "get_file_history":
                return json.dumps(
                    await self.get_file_history(arguments["path"], int(arguments.get("limit", 10)))
                )
            return f"Unknown tool: {name}"
        except Exception as exc:  # noqa: BLE001
            return f"Tool '{name}' failed: {exc}"


def get_tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a markdown file in the vault.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Vault-relative file path (e.g. 'notes/example.md')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write markdown content to a file in the vault.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Vault-relative file path (e.g. 'notes/example.md')",
                        },
                        "content": {"type": "string", "description": "The full file content to write."},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files in the vault matching a glob pattern.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "glob_pattern": {
                            "type": "string",
                            "description": "Glob pattern relative to vault root (default '**/*.md').",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_files",
                "description": "Search vault files for a text query and return contextual snippets.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Case-insensitive substring query."},
                        "glob_pattern": {
                            "type": "string",
                            "description": "Glob pattern relative to vault root (default '**/*.md').",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_url",
                "description": "Fetch text content from an HTTP URL.",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "Absolute URL to fetch."}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "undo_last_change",
                "description": "Undo the most recent Jujutsu change in the vault.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_file_history",
                "description": "Return recent change history entries for a vault file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Vault-relative file path (e.g. 'notes/example.md').",
                        },
                        "limit": {"type": "integer", "description": "Maximum number of entries to return."},
                    },
                    "required": ["path"],
                },
            },
        },
    ]
