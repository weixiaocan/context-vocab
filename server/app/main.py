from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import collect, dictionary, review
from app.config import load_settings
from app.db import connect, init_db
from app.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="Vocab Flashcard")
    app.state.settings = settings
    app.state.db = connect(settings.db_path)
    init_db(app.state.db)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(dictionary.router)
    app.include_router(collect.router)
    app.include_router(review.router)

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.on_event("startup")
    def on_startup() -> None:
        app.state.scheduler = start_scheduler(settings)

    @app.on_event("shutdown")
    def on_shutdown() -> None:
        app.state.db.close()
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler:
            scheduler.shutdown(wait=False)

    return app


app = create_app()
