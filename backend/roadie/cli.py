"""Linha de comando do Roadie.

    roadie db wait        espera o banco responder
    roadie db init        cria o schema
    roadie seed           carrega CSVs e manual (em breve)
    roadie create-admin   cria o primeiro administrador (em breve)
"""

from __future__ import annotations

import asyncio
import time

import typer
from rich.console import Console
from sqlalchemy import text

from roadie.config import get_settings

app = typer.Typer(help="Roadie — agente de atendimento da Empório da Música", no_args_is_help=True)
db_app = typer.Typer(help="Operações de banco de dados", no_args_is_help=True)
app.add_typer(db_app, name="db")
console = Console()


async def _ping() -> None:
    from roadie.db.engine import get_engine

    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))


@db_app.command("wait")
def db_wait(timeout: int = typer.Option(60, help="segundos até desistir")) -> None:
    """Espera o PostgreSQL aceitar conexões."""
    deadline = time.monotonic() + timeout
    attempt = 0
    while True:
        attempt += 1
        try:
            asyncio.run(_ping())
            console.print(f"[green]banco disponível[/green] (tentativa {attempt})")
            return
        except Exception as exc:  # noqa: BLE001
            if time.monotonic() > deadline:
                console.print(f"[red]banco indisponível após {timeout}s:[/red] {exc}")
                raise typer.Exit(code=1) from exc
            time.sleep(2)


async def _init_schema() -> None:
    from roadie.db.engine import get_engine
    from roadie.db.models import Base

    async with get_engine().begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)


@db_app.command("init")
def db_init() -> None:
    """Cria extensões e tabelas (idempotente)."""
    asyncio.run(_init_schema())
    console.print("[green]schema pronto[/green]")


@app.command("seed")
def seed(if_empty: bool = typer.Option(False, "--if-empty", help="só carrega se o banco estiver vazio")) -> None:
    """Carrega os CSVs e o manual de políticas no banco."""
    console.print("[yellow]seed ainda não implementado nesta versão[/yellow]")


@app.command("create-admin")
def create_admin(if_missing: bool = typer.Option(False, "--if-missing")) -> None:
    """Cria o primeiro administrador a partir de ADMIN_EMAIL / ADMIN_PASSWORD."""
    console.print("[yellow]create-admin ainda não implementado nesta versão[/yellow]")


@app.command("info")
def info() -> None:
    """Mostra a configuração efetiva (sem segredos)."""
    s = get_settings()
    console.print(
        {
            "env": s.app_env,
            "database": s.database_url.split("@")[-1],
            "llm_mode": s.llm_mode,
            "models": [s.openai_model_primary, s.openai_model_fallback],
            "store_clock": s.store_clock,
            "timezone": s.store_timezone,
            "data_dir": str(s.data_dir),
        }
    )


if __name__ == "__main__":
    app()
