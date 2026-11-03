"""Construção do modelo de linguagem: OpenAI com fallback, simulado ou não configurado.

Também expõe o teste de conexão usado pelo console: autentica, confere se os
modelos configurados aparecem na conta e faz uma chamada mínima.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from roadie.config import Settings
from roadie.llm_config import LLMConfig


class LLMNotConfigured(RuntimeError):
    """Nenhuma chave da OpenAI disponível, nem no banco nem no ambiente."""


@dataclass
class ModelBundle:
    with_tools: Runnable | None
    plain: Runnable | None
    primary_name: str
    fallback_name: str | None
    mode: str  # openai | mock | unconfigured
    key_source: str | None = None


def build_models(settings: Settings, tools: list) -> ModelBundle:
    """Constrói a partir do ambiente apenas (sem consultar o banco)."""
    return build_models_from_config(LLMConfig.from_settings(settings), tools)


def build_models_from_config(cfg: LLMConfig, tools: list) -> ModelBundle:
    if cfg.mode == "mock":
        from roadie.agent.mock_llm import MockTom

        mock = MockTom()
        return ModelBundle(
            with_tools=mock, plain=mock, primary_name="mock-tom", fallback_name=None, mode="mock"
        )
    if not cfg.api_key:
        return ModelBundle(
            with_tools=None,
            plain=None,
            primary_name=cfg.primary,
            fallback_name=cfg.fallback,
            mode="unconfigured",
        )

    from langchain_openai import ChatOpenAI

    def make(model: str) -> BaseChatModel:
        return ChatOpenAI(
            model=model, api_key=cfg.api_key, timeout=cfg.timeout_seconds, max_retries=2
        )

    primary = make(cfg.primary)
    fallback = make(cfg.fallback) if cfg.fallback else None
    with_tools: Runnable = primary.bind_tools(tools)
    plain: Runnable = primary
    if fallback is not None:
        with_tools = with_tools.with_fallbacks([fallback.bind_tools(tools)])
        plain = plain.with_fallbacks([fallback])
    return ModelBundle(
        with_tools=with_tools,
        plain=plain,
        primary_name=cfg.primary,
        fallback_name=cfg.fallback,
        mode="openai",
        key_source=cfg.key_source,
    )


def describe_error(exc: Exception) -> str:
    from openai import (
        APIConnectionError,
        APIStatusError,
        AuthenticationError,
        NotFoundError,
        RateLimitError,
    )

    if isinstance(exc, AuthenticationError):
        return "chave inválida ou revogada (401)"
    if isinstance(exc, RateLimitError):
        return "limite de uso atingido ou conta sem créditos (429)"
    if isinstance(exc, NotFoundError):
        return "modelo não encontrado para esta conta (404)"
    if isinstance(exc, APIConnectionError):
        return "sem conexão com a API da OpenAI"
    if isinstance(exc, APIStatusError):
        return f"erro HTTP {exc.status_code} da API da OpenAI"
    return f"{type(exc).__name__}: {str(exc)[:160]}"


async def test_connection(
    api_key: str, primary: str, fallback: str | None, timeout: float = 25.0
) -> dict:
    """Três passos: autenticação, modelos visíveis na conta e uma chamada mínima."""
    from openai import AsyncOpenAI

    result: dict = {
        "ok": False,
        "steps": [],
        "warnings": [],
        "models": {"primary": primary, "fallback": fallback},
    }
    client = AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=0)
    started = perf_counter()
    try:
        listing = await client.models.list()
        ids = {m.id for m in listing.data}
        result["steps"].append(
            {
                "step": "autenticacao",
                "ok": True,
                "detail": f"chave aceita; {len(ids)} modelos visíveis na conta",
            }
        )
    except Exception as exc:  # noqa: BLE001
        msg = describe_error(exc)
        result["steps"].append({"step": "autenticacao", "ok": False, "detail": msg})
        result["error"] = msg
        result["latency_ms"] = round((perf_counter() - started) * 1000)
        return result

    for label, model in (("primario", primary), ("fallback", fallback)):
        if not model:
            continue
        visible = model in ids or any(i.startswith(model) for i in ids)
        result["steps"].append(
            {
                "step": f"modelo_{label}",
                "ok": visible,
                "detail": f"{model}: "
                + ("disponível na conta" if visible else "não aparece na lista da conta"),
            }
        )
        if not visible:
            result["warnings"].append(f"modelo {label} '{model}' não aparece na lista da conta")

    call_ok = False
    try:
        t0 = perf_counter()
        resp = await client.responses.create(
            model=primary, input="Responda apenas com a palavra: ok", max_output_tokens=64
        )
        text = (getattr(resp, "output_text", "") or "").strip()
        usage = getattr(resp, "usage", None)
        detail = f"{resp.model} respondeu em {round((perf_counter() - t0) * 1000)} ms"
        if text:
            detail += f": {text[:40]}"
        result["steps"].append({"step": "chamada_minima", "ok": True, "detail": detail})
        result["model_used"] = resp.model
        if usage is not None:
            result["tokens"] = {
                "input": getattr(usage, "input_tokens", None),
                "output": getattr(usage, "output_tokens", None),
            }
        call_ok = True
    except Exception as exc:  # noqa: BLE001
        msg = describe_error(exc)
        result["steps"].append({"step": "chamada_minima", "ok": False, "detail": msg})
        result["error"] = msg

    result["ok"] = call_ok
    result["latency_ms"] = round((perf_counter() - started) * 1000)
    return result
