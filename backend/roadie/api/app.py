"""Fábrica da aplicação FastAPI."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from roadie import __version__
from roadie.api.deps import limiter
from roadie.api.routers import auth, conversations, llm, operations, users
from roadie.clock import get_clock
from roadie.config import get_settings
from roadie.db.engine import dispose_engine, get_engine

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.is_prod and settings.secret_key.startswith("troque-"):
        raise RuntimeError("SECRET_KEY padrão em produção. Gere um segredo real no .env.")

    app = FastAPI(
        title="Roadie — Empório da Música",
        version=__version__,
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    app.include_router(auth.router)
    app.include_router(conversations.router)
    app.include_router(operations.router)
    app.include_router(users.router)
    app.include_router(llm.router)

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
