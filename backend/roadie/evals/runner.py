"""Executa os cenários contra o agente e escreve as conversas de exemplo.

Saída, por cenário, um Markdown com o diálogo completo e, para cada resposta
do Tom, o bloco de bastidores (ferramentas, cláusulas, regras, modelo, custo)
e o resultado das expectativas. Um índice resume tudo.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from roadie.agent.service import TomService
from roadie.clock import StoreClock
from roadie.evals.scenarios import SCENARIOS, Scenario, Turn


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


@dataclass
class Check:
    label: str
    ok: bool


@dataclass
class TurnResult:
    turn: Turn
    reply: str
    receipt: dict
    checks: list[Check]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


@dataclass
class ScenarioResult:
    scenario: Scenario
    conversation_id: str
    turns: list[TurnResult] = field(default_factory=list)
    error: str | None = None

    @property
    def checks_total(self) -> int:
        return sum(len(t.checks) for t in self.turns)

    @property
    def checks_ok(self) -> int:
        return sum(1 for t in self.turns for c in t.checks if c.ok)

    @property
    def cost_usd(self) -> float | None:
        costs = [t.receipt.get("cost_usd") for t in self.turns]
        if any(c is None for c in costs):
            return None
        return round(sum(costs), 6)

    @property
    def tokens(self) -> int:
        return sum(int(t.receipt.get("tokens", {}).get("total", 0)) for t in self.turns)


def evaluate(turn: Turn, reply: str, receipt: dict) -> list[Check]:
    checks: list[Check] = []
    tools_called = [t["name"] for t in receipt.get("tools", [])]
    folded = _fold(reply)
    for tool in turn.expect_tools:
        checks.append(Check(f"chamou {tool}", tool in tools_called))
    if turn.expect_any:
        hit = any(_fold(s) in folded for s in turn.expect_any)
        checks.append(
            Check("resposta menciona " + " | ".join(f"“{s}”" for s in turn.expect_any), hit)
        )
    for s in turn.expect_none:
        checks.append(Check(f"resposta não menciona “{s}”", _fold(s) not in folded))
    clauses = receipt.get("sources", {}).get("clauses", [])
    for c in turn.expect_clauses:
        checks.append(Check(f"cita cláusula {c}", c in clauses))
    if turn.expect_ticket is not None:
        has = bool(receipt.get("tickets"))
        checks.append(
            Check(
                "abriu ticket" if turn.expect_ticket else "não abriu ticket",
                has == turn.expect_ticket,
            )
        )
    return checks


async def run_scenario(
    service: TomService, scenario: Scenario, *, verbose: bool = False
) -> ScenarioResult:
    clock = datetime.fromisoformat(scenario.clock)
    conv = await service.start_conversation(
        scenario.sender_phone, clock_override=clock, channel="evals"
    )
    result = ScenarioResult(scenario=scenario, conversation_id=str(conv.id))
    for turn in scenario.turns:
        try:
            reply = await service.send(conv.id, turn.text)
        except Exception as exc:  # noqa: BLE001
            result.error = f"{type(exc).__name__}: {exc}"
            break
        checks = evaluate(turn, reply.content, reply.receipt)
        result.turns.append(
            TurnResult(turn=turn, reply=reply.content, receipt=reply.receipt, checks=checks)
        )
        if verbose:
            status = "ok" if all(c.ok for c in checks) else "FALHOU"
            print(f"  [{status}] cliente: {turn.text}")
            print(f"           tom: {reply.content[:160].replace(chr(10), ' ')}")
    return result


# ----------------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------------
def _args_md(args: dict) -> str:
    compact = {k: v for k, v in args.items() if v not in (None, "", [])}
    return json.dumps(compact, ensure_ascii=False) if compact else "{}"


def render_scenario(res: ScenarioResult, index: int, model_label: str) -> str:
    s = res.scenario
    clock = StoreClock.describe(datetime.fromisoformat(s.clock))
    lines: list[str] = []
    lines.append(f"# {index}. {s.title}")
    lines.append("")
    lines.append(s.description)
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append(f"| Remetente | `{s.sender_phone or 'sem número'}` |")
    lines.append(f"| Relógio da loja | {clock} |")
    lines.append(f"| Modelo | `{model_label}` |")
    lines.append(f"| Conversa | `{res.conversation_id}` |")
    lines.append(f"| Verificações | {res.checks_ok}/{res.checks_total} |")
    if res.cost_usd is not None:
        lines.append(f"| Custo estimado | US$ {res.cost_usd:.4f} ({res.tokens} tokens) |")
    if s.nontrivial:
        lines.append("| Situação não trivial | sim: dados em tempo real e regras do manual |")
    lines.append("")
    lines.append("## Conversa")
    lines.append("")
    for i, t in enumerate(res.turns, start=1):
        lines.append(f"**Cliente:** {t.turn.text}")
        lines.append("")
        lines.append("**Tom:** " + t.reply.strip().replace("\n", "  \n"))
        lines.append("")
        r = t.receipt
        tools = r.get("tools", [])
        src = r.get("sources", {})
        model = r.get("model", {})
        cost = r.get("cost_usd")
        lines.append("<details>")
        summary = f"Bastidores da resposta {i}: {len(tools)} consulta(s)"
        if src.get("clauses"):
            summary += f", cláusulas {', '.join(src['clauses'])}"
        summary += f", {r.get('latency_ms', 0) / 1000:.1f} s"
        lines.append(f"<summary>{summary}</summary>")
        lines.append("")
        if t.turn.note:
            lines.append(f"> {t.turn.note}")
            lines.append("")
        if tools:
            lines.append("| # | Ferramenta | Argumentos | Resultado |")
            lines.append("|---|---|---|---|")
            for n, tool in enumerate(tools, start=1):
                res_ = tool.get("result") or {}
                status = "✅" if res_.get("ok", True) else "⚠️"
                summ = (res_.get("summary") or "").replace("|", "/")
                ms = res_.get("duration_ms")
                lines.append(
                    f"| {n} | `{tool['name']}` | `{_args_md(tool.get('args', {})).replace('|', '/')}` | {status} {summ} ({ms} ms) |"
                )
            lines.append("")
        facts = []
        if src.get("tables"):
            facts.append("tabelas: " + ", ".join(f"`{x}`" for x in src["tables"]))
        if src.get("rows"):
            facts.append(
                "linhas: "
                + ", ".join(f"`{x['table']}#{x['id']}`" for x in src["rows"][:12])
                + (" …" if len(src["rows"]) > 12 else "")
            )
        if src.get("clauses"):
            facts.append("cláusulas do manual: " + ", ".join(f"`§{x}`" for x in src["clauses"]))
        if src.get("rules"):
            facts.append("regras determinísticas: " + ", ".join(f"`{x}`" for x in src["rules"]))
        if r.get("flags"):
            facts.append("sinalizações: " + ", ".join(f"`{x}`" for x in r["flags"]))
        if r.get("tickets"):
            facts.append(
                "tickets: "
                + ", ".join(f"`{x['protocolo']}` ({x['categoria']})" for x in r["tickets"])
            )
        ident = r.get("identity", {})
        facts.append(
            "identidade: "
            + (
                f"{ident.get('name')} (verificado por {ident.get('via')})"
                if ident.get("verified")
                else "não identificado"
            )
        )
        facts.append(
            f"modelo: `{', '.join(model.get('used') or [model.get('primary', '?')])}`"
            + (" (fallback acionado)" if model.get("fallback_used") else "")
            + f" · {r.get('tokens', {}).get('total', 0)} tokens"
            + (f" · US$ {cost:.4f}" if cost is not None else "")
        )
        for f in facts:
            lines.append(f"- {f}")
        lines.append("")
        lines.append("Verificações:")
        lines.append("")
        for c in t.checks:
            lines.append(f"- {'✅' if c.ok else '❌'} {c.label}")
        lines.append("")
        lines.append("</details>")
        lines.append("")
    if res.error:
        lines.append(f"> ⚠️ A execução parou com erro: `{res.error}`")
        lines.append("")
    return "\n".join(lines)


def render_index(results: list[ScenarioResult], model_label: str, generated_at: datetime) -> str:
    lines = [
        "# Conversas de exemplo",
        "",
        "Transcrições reais geradas pelo comando `roadie evals`, que roda cenários roteirizados contra o agente "
        "e confere, a cada resposta, as ferramentas chamadas, as cláusulas citadas e trechos esperados. "
        "Cada resposta do Tom traz um bloco *Bastidores* com o recibo de evidências.",
        "",
        f"Gerado em {generated_at.astimezone().strftime('%d/%m/%Y %H:%M')} com o modelo `{model_label}`.",
        "",
        "| # | Cenário | Turnos | Verificações | Custo | Não trivial |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, start=1):
        cost = f"US$ {r.cost_usd:.4f}" if r.cost_usd is not None else "—"
        lines.append(
            f"| {i} | [{r.scenario.title}]({i:02d}-{r.scenario.slug}.md) | {len(r.turns)} | {r.checks_ok}/{r.checks_total} | {cost} | {'sim' if r.scenario.nontrivial else ''} |"
        )
    total_cost = sum(r.cost_usd for r in results if r.cost_usd is not None)
    lines.append("")
    lines.append(f"Custo total estimado: US$ {total_cost:.4f}.")
    lines.append("")
    return "\n".join(lines)


async def run_all(
    service: TomService,
    out_dir: Path,
    *,
    only: list[str] | None = None,
    verbose: bool = True,
) -> list[ScenarioResult]:
    out_dir.mkdir(parents=True, exist_ok=True)
    models = await service.ensure_models()
    model_label = models.primary_name if models.mode == "openai" else models.mode
    selected = [s for s in SCENARIOS if not only or s.slug in only]
    results: list[ScenarioResult] = []
    for i, scenario in enumerate(selected, start=1):
        if verbose:
            print(f"\n== {i}. {scenario.title}")
        res = await run_scenario(service, scenario, verbose=verbose)
        results.append(res)
        path = out_dir / f"{i:02d}-{scenario.slug}.md"
        path.write_text(render_scenario(res, i, model_label), encoding="utf-8", newline="\n")
        if verbose:
            print(f"   -> {path} ({res.checks_ok}/{res.checks_total} verificações)")
    (out_dir / "README.md").write_text(
        render_index(results, model_label, datetime.now(UTC)), encoding="utf-8", newline="\n"
    )
    return results
