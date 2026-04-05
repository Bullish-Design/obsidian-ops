from __future__ import annotations

import uvicorn

from obsidian_ops.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run("obsidian_ops.app:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
