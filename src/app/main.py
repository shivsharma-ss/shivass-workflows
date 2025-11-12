"""FastAPI application factory."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import get_settings
from app.routes import router
from services.container import AppContainer

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

LANDING_PAGE = Path(__file__).resolve().parents[2] / "submit-cv.html"


def create_app() -> FastAPI:
    """Instantiate the FastAPI app and wire dependencies."""

    settings = get_settings()
    container = AppContainer(settings)
    app = FastAPI(title="CV-JD Alignment Orchestrator", version="0.1.0")
    allowed_origins = list(dict.fromkeys(settings.cors_origins + [settings.frontend_base_url]))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.state.container = container  # type: ignore[attr-defined]

    @app.get("/", include_in_schema=False)
    async def landing_page() -> FileResponse:
        if not LANDING_PAGE.exists():
            raise HTTPException(status_code=404, detail="Landing page not found")
        return FileResponse(LANDING_PAGE, media_type="text/html")

    @app.get("/healthz")
    async def health() -> dict[str, str]:  # pragma: no cover - trivial
        return {"status": "ok"}

    @app.on_event("startup")
    async def on_startup() -> None:
        await container.startup()

    return app
