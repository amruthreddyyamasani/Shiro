"""Console entry point for running Shiro on localhost."""

from __future__ import annotations

import uvicorn

from .config import Settings


def main() -> None:
    settings = Settings.load()
    uvicorn.run(
        "shiro.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
