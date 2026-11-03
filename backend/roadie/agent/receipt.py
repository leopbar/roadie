"""Recibo de evidências de uma resposta do Tom.

Para cada mensagem do assistente, o recibo diz: que ferramentas foram chamadas
e com quais argumentos, quais tabelas e linhas foram lidas, quais cláusulas do
manual sustentam a resposta, quais regras determinísticas rodaram, se houve
sinalização de qualidade, que modelo respondeu (e se foi o fallback), quantos
tokens custou e quanto tempo levou.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

from roadie.agent.context import RunContext
from roadie.agent.pricing import PRICES_AS_OF, estimate_cost_usd
from roadie.clock import StoreClock


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


def final_answer(messages: list[AnyMessage]) -> str | None:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not m.tool_calls:
            text = _text(m.content).strip()
            if text:
                return text
    return None


def build_receipt(
    messages: list[AnyMessage],
    *,
    ctx: RunContext,
    primary_model: str,
    latency_ms: float,
    mode: str,
) -> dict:
    tool_calls: dict[str, dict] = {}
    order: list[str] = []
    tables: list[str] = []
    rows: list[dict] = []
    clauses: list[str] = []
    rules_used: list[str] = []
    flags: list[str] = []
    tickets: list[dict] = []
    identity_update: dict | None = None
    models: list[str] = []
    tokens = {"input": 0, "output": 0, "total": 0}
    cost = 0.0
    cost_known = True
    llm_calls = 0

    def add_unique(target: list, items) -> None:
        for item in items:
            if item not in target:
                target.append(item)

    for m in messages:
        if isinstance(m, AIMessage):
            llm_calls += 1
            model = (m.response_metadata or {}).get("model_name") or (
                m.response_metadata or {}
            ).get("model")
            if model:
                add_unique(models, [model])
            usage = m.usage_metadata or {}
            tokens["input"] += int(usage.get("input_tokens", 0) or 0)
            tokens["output"] += int(usage.get("output_tokens", 0) or 0)
            tokens["total"] += int(usage.get("total_tokens", 0) or 0)
            est = estimate_cost_usd(
                model,
                int(usage.get("input_tokens", 0) or 0),
                int(usage.get("output_tokens", 0) or 0),
            )
            if est is None:
                cost_known = False
            else:
                cost += est
            for call in m.tool_calls or []:
                entry = {
                    "id": call.get("id"),
                    "name": call.get("name"),
                    "args": call.get("args", {}),
                    "result": None,
                }
                tool_calls[entry["id"]] = entry
                order.append(entry["id"])
        elif isinstance(m, ToolMessage):
            artifact = m.artifact if isinstance(m.artifact, dict) else {}
            entry = tool_calls.get(m.tool_call_id)
            if entry is None:
                entry = {"id": m.tool_call_id, "name": m.name, "args": {}, "result": None}
                tool_calls[m.tool_call_id] = entry
                order.append(m.tool_call_id)
            entry["result"] = {
                "ok": artifact.get("ok", m.status == "success"),
                "summary": artifact.get("summary") or _text(m.content)[:160],
                "duration_ms": artifact.get("duration_ms"),
            }
            add_unique(tables, artifact.get("tables", []))
            add_unique(rows, artifact.get("rows", []))
            add_unique(clauses, artifact.get("clauses", []))
            add_unique(rules_used, artifact.get("rules", []))
            add_unique(flags, artifact.get("flags", []))
            if artifact.get("ticket"):
                tickets.append(artifact["ticket"])
            if artifact.get("identity_update"):
                identity_update = artifact["identity_update"]

    fallback_used = (
        bool(models) and all(not mdl.startswith(primary_model) for mdl in models)
        if mode == "openai"
        else False
    )
    return {
        "version": 1,
        "clock": {"now": ctx.now.isoformat(), "label": StoreClock.describe(ctx.now)},
        "identity": ctx.identity.as_dict(),
        "identity_update": identity_update,
        "tools": [tool_calls[i] for i in order],
        "sources": {"tables": tables, "rows": rows, "clauses": clauses, "rules": rules_used},
        "flags": flags,
        "tickets": tickets,
        "model": {
            "mode": mode,
            "primary": primary_model,
            "used": models,
            "fallback_used": fallback_used,
            "llm_calls": llm_calls,
        },
        "tokens": tokens,
        "cost_usd": round(cost, 6) if cost_known else None,
        "pricing_as_of": PRICES_AS_OF,
        "latency_ms": round(latency_ms, 1),
    }
