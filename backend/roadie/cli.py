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
    asyncio.run(_create_admin(if_missing))


async def _create_admin(if_missing: bool) -> None:
    from sqlalchemy import select

    from roadie.auth.security import AuthError, hash_password, validate_password_strength
    from roadie.db.engine import session_scope
    from roadie.db.models import User, UserRole

    s = get_settings()
    if not s.admin_email or not s.admin_password:
        if if_missing:
            console.print(
                "[yellow]ADMIN_EMAIL/ADMIN_PASSWORD não definidos; nenhum admin criado[/yellow]"
            )
            return
        console.print("[red]defina ADMIN_EMAIL e ADMIN_PASSWORD no .env[/red]")
        raise typer.Exit(code=2)
    email = s.admin_email.lower()
    async with session_scope() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing:
            console.print(f"[yellow]admin já existe:[/yellow] {existing.email}")
            return
        try:
            validate_password_strength(s.admin_password)
        except AuthError as exc:
            console.print(f"[red]senha do admin fraca:[/red] {exc}")
            raise typer.Exit(code=2) from exc
        session.add(
            User(
                email=email,
                name=s.admin_name,
                password_hash=hash_password(s.admin_password),
                role=UserRole.admin,
            )
        )
    console.print(f"[green]admin criado:[/green] {email}")


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


# ----------------------------------------------------------------------------
# conversar com o Tom
# ----------------------------------------------------------------------------
def _print_receipt(receipt: dict) -> None:
    from rich.panel import Panel

    tools = receipt.get("tools", [])
    lines = []
    for t in tools:
        res = t.get("result") or {}
        status = "ok" if res.get("ok", True) else "erro"
        lines.append(
            f"[cyan]{t['name']}[/cyan]({t.get('args')}) -> {res.get('summary')} [{status}, {res.get('duration_ms')} ms]"
        )
    src = receipt.get("sources", {})
    model = receipt.get("model", {})
    lines.append(
        f"[dim]tabelas={src.get('tables')} cláusulas={src.get('clauses')} regras={src.get('rules')} "
        f"flags={receipt.get('flags')} tickets={[t.get('protocolo') for t in receipt.get('tickets', [])]}[/dim]"
    )
    cost = receipt.get("cost_usd")
    cost_label = f"US$ {cost:.5f}" if cost is not None else "?"
    lines.append(
        f"[dim]modelo={model.get('used')} fallback={model.get('fallback_used')} tokens={receipt.get('tokens', {}).get('total')} "
        f"custo={cost_label} latência={receipt.get('latency_ms')} ms "
        f"relógio={receipt.get('clock', {}).get('label')} identidade={receipt.get('identity', {}).get('name')}[/dim]"
    )
    console.print(Panel(chr(10).join(lines), title="bastidores", border_style="yellow"))


def _parse_now(value: str | None):
    from datetime import datetime

    return datetime.fromisoformat(value) if value else None


async def _ask(
    text: str, phone: str | None, now: str | None, conversation: str | None, show_receipt: bool
) -> None:
    import uuid

    from roadie.agent.service import TomService

    service = TomService()
    if conversation:
        conv_id = uuid.UUID(conversation)
    else:
        conv = await service.start_conversation(phone, clock_override=_parse_now(now))
        conv_id = conv.id
    reply = await service.send(conv_id, text)
    console.print(f"[bold green]Tom:[/bold green] {reply.content}")
    console.print(f"[dim]conversa {conv_id}[/dim]")
    if show_receipt:
        _print_receipt(reply.receipt)


@app.command("ask")
def ask(
    text: str = typer.Argument(..., help="mensagem do cliente"),
    phone: str = typer.Option(
        None, "--phone", "-p", help="telefone do remetente (como no WhatsApp)"
    ),
    now: str = typer.Option(
        None, "--now", help="relógio simulado da conversa, ISO (ex.: 2026-03-24T10:00)"
    ),
    conversation: str = typer.Option(None, "--conversation", "-c", help="id de conversa existente"),
    receipt: bool = typer.Option(
        True, "--receipt/--no-receipt", help="mostra o recibo de evidências"
    ),
) -> None:
    """Envia uma mensagem ao Tom e mostra a resposta com o recibo de evidências."""
    asyncio.run(_ask(text, phone, now, conversation, receipt))


async def _chat(phone: str | None, now: str | None, show_receipt: bool) -> None:
    from roadie.agent.service import TomService

    service = TomService()
    conv = await service.start_conversation(phone, clock_override=_parse_now(now))
    label = "identificado" if conv.identity_verified else "não identificado"
    console.print(
        f"[bold]Roadie[/bold] — conversa {conv.id} | remetente {phone or 'desconhecido'} ({label}) | modelo {service.models.mode}"
    )
    console.print("[dim]Digite a mensagem do cliente. Ctrl+C ou 'sair' para encerrar.[/dim]")
    while True:
        try:
            text = console.input("[bold magenta]cliente>[/bold magenta] ")
        except (EOFError, KeyboardInterrupt):
            break
        if text.strip().lower() in {"sair", "exit", "quit"}:
            break
        if not text.strip():
            continue
        try:
            reply = await service.send(conv.id, text)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]erro:[/red] {exc}")
            continue
        console.print(f"[bold green]Tom:[/bold green] {reply.content}")
        if show_receipt:
            _print_receipt(reply.receipt)


@app.command("chat")
def chat(
    phone: str = typer.Option(
        None, "--phone", "-p", help="telefone do remetente (como no WhatsApp)"
    ),
    now: str = typer.Option(
        None, "--now", help="relógio simulado da conversa, ISO (ex.: 2026-03-24T10:00)"
    ),
    receipt: bool = typer.Option(
        True, "--receipt/--no-receipt", help="mostra o recibo após cada resposta"
    ),
) -> None:
    """Conversa interativa com o Tom no terminal."""
    asyncio.run(_chat(phone, now, receipt))


if __name__ == "__main__":
    app()
