"""Aplicação FastAPI do Roadie."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from roadie import __version__
from roadie.clock import get_clock
from roadie.config import get_settings
from roadie.db.engine import dispose_engine, get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Roadie — Empório da Música",
        version=__version__,
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.get("/health", tags=["infra"])
    async def health() -> dict:
        clock = get_clock()
        now = clock.now()
        return {
            "status": "ok",
            "version": __version__,
            "env": settings.app_env,
            "clock": {
                "now": now.isoformat(),
                "simulated": clock.is_simulated,
                "label": clock.describe(now),
            },
        }

    return app


app = create_app()
