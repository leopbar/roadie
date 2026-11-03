"""Configuração central lida do ambiente (.env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["dev", "prod", "test"] = "dev"

    # banco
    database_url: str = "postgresql+asyncpg://roadie:roadie@localhost:5432/roadie"

    # segurança
    secret_key: str = "troque-por-um-segredo-longo-e-aleatorio"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000"  # separado por vírgula
    rate_limit_login: str = "5/minute"
    rate_limit_chat: str = "30/minute"

    # bootstrap do admin
    admin_email: str | None = None
    admin_password: str | None = None
    admin_name: str = "Gerência"

    # LLM
    openai_api_key: str | None = None
    openai_model_primary: str = "gpt-6.1-terra"
    openai_model_fallback: str = "gpt-6-luna"
    llm_mode: Literal["openai", "mock"] = "openai"
    llm_timeout_seconds: float = 60.0
    max_tool_rounds: int = 6

    # relógio da loja
    store_timezone: str = "America/Campo_Grande"
    store_clock: str = "2026-03-24T10:00:00"  # ou "real"

    # dados de entrada
    data_dir: Path = REPO_ROOT / "data"

    @property
    def cors_origin_list(self) -> list[str]:
        return [v.strip() for v in self.cors_origins.split(",") if v.strip()]

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
