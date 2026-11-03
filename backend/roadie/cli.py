"""Linha de comando do Roadie.

roadie db wait          espera o banco responder
roadie db init          cria extensões e tabelas
roadie seed             carrega CSVs + manual no banco (com quarentena)
roadie quality          mostra as sinalizações de qualidade (sem banco)
roadie policies         mostra as cláusulas extraídas do manual (sem banco)
roadie create-admin     cria o primeiro administrador
roadie info             configuração efetiva
"""

from __future__ import annotations

import asyncio
import time

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from roadie.config import get_settings

app = typer.Typer(help="Roadie — agente de atendimento da Empório da Música", no_args_is_help=True)
db_app = typer.Typer(help="Operações de banco de dados", no_args_is_help=True)
app.add_typer(db_app, name="db")
console = Console()


# ----------------------------------------------------------------------------
# banco
# ----------------------------------------------------------------------------
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


# ----------------------------------------------------------------------------
# ingestão
# ----------------------------------------------------------------------------
async def _seed(if_empty: bool, replace: bool) -> None:
    from roadie.db.engine import session_scope
    from roadie.db.seed import is_empty, prepare, seed_database, truncate_store_tables

    settings = get_settings()
    dataset, clauses, flags = prepare(settings.data_dir)

    async with session_scope() as session:
        empty = await is_empty(session)
        if not empty and if_empty:
            console.print("[yellow]banco já carregado; nada a fazer (--if-empty)[/yellow]")
            return
        if not empty and not replace:
            console.print("[red]banco já carregado.[/red] Use --replace para recarregar.")
            raise typer.Exit(code=2)
        if not empty:
            await truncate_store_tables(session)
        report = await seed_database(session, dataset, clauses, flags)

    table = Table(title="Carga concluída", show_lines=False)
    table.add_column("tabela")
    table.add_column("linhas", justify="right")
    for name, n in report.counts.items():
        table.add_row(name, str(n))
    table.add_row("policy_clauses", str(report.clauses))
    table.add_row("data_quality_flags", str(sum(report.flags_by_severity.values())))
    console.print(table)
    console.print("sinalizações por severidade:", report.flags_by_severity)


@app.command("seed")
def seed(
    if_empty: bool = typer.Option(False, "--if-empty", help="só carrega se o banco estiver vazio"),
    replace: bool = typer.Option(False, "--replace", help="apaga e recarrega as tabelas da loja"),
) -> None:
    """Carrega os CSVs e o manual de políticas no banco."""
    asyncio.run(_seed(if_empty=if_empty, replace=replace))


@app.command("quality")
def quality(
    severity: str = typer.Option("", help="filtra por severidade: info | warning | quarantine"),
) -> None:
    """Roda a quarentena de dados sobre os CSVs e mostra o resultado (não usa banco)."""
    from roadie.ingest.csv_loader import load_dataset
    from roadie.ingest.quality import run_all

    settings = get_settings()
    ds = load_dataset(settings.data_dir)
    flags = run_all(ds)
    if severity:
        flags = [f for f in flags if f.severity.value == severity]
    table = Table(title=f"Qualidade de dados — {len(flags)} sinalizações")
    table.add_column("entidade")
    table.add_column("id", justify="right")
    table.add_column("sinalização")
    table.add_column("severidade")
    table.add_column("detalhe")
    colors = {"quarantine": "red", "warning": "yellow", "info": "cyan"}
    for f in flags:
        table.add_row(
            f.entity,
            f.entity_id,
            f.flag,
            f"[{colors[f.severity.value]}]{f.severity.value}[/]",
            f.detail,
        )
    console.print(table)


@app.command("policies")
def policies(
    full: bool = typer.Option(False, "--full", help="mostra o corpo das cláusulas"),
) -> None:
    """Extrai o manual de políticas em cláusulas e mostra o sumário (não usa banco)."""
    from roadie.ingest.policy_pdf import find_policy_pdf, load_policy_clauses

    settings = get_settings()
    pdf = find_policy_pdf(settings.data_dir)
    clauses = load_policy_clauses(pdf)
    console.print(f"[bold]{pdf.name}[/bold] — {len(clauses)} cláusulas")
    for c in clauses:
        indent = "  " if "." in c.clause_id else ""
        console.print(
            f"{indent}[cyan]{c.clause_id:>4}[/cyan]  {c.title}  [dim](p.{c.page}, {len(c.body)} chars)[/dim]"
        )
        if full:
            console.print(f"[dim]{c.body}[/dim]\n")


# ----------------------------------------------------------------------------
# usuários
# ----------------------------------------------------------------------------
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
