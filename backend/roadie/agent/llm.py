"""Construção do modelo de linguagem: OpenAI com fallback, ou simulado."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from roadie.config import Settings


@dataclass
class ModelBundle:
    with_tools: Runnable
    plain: Runnable
    primary_name: str
    fallback_name: str | None
    mode: str


def build_models(settings: Settings, tools: list) -> ModelBundle:
    if settings.llm_mode == "mock":
        from roadie.agent.mock_llm import MockTom

        mock = MockTom()
        return ModelBundle(
            with_tools=mock, plain=mock, primary_name="mock-tom", fallback_name=None, mode="mock"
        )

    from langchain_openai import ChatOpenAI

    if not settings.openai_api_key or settings.openai_api_key.startswith("sk-..."):
        raise RuntimeError("OPENAI_API_KEY não configurada. Defina no .env ou use LLM_MODE=mock.")

    def make(model: str) -> BaseChatModel:
        return ChatOpenAI(
            model=model,
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    primary = make(settings.openai_model_primary)
    fallback = make(settings.openai_model_fallback) if settings.openai_model_fallback else None

    with_tools: Runnable = primary.bind_tools(tools)
    plain: Runnable = primary
    if fallback is not None:
        with_tools = with_tools.with_fallbacks([fallback.bind_tools(tools)])
        plain = plain.with_fallbacks([fallback])
    return ModelBundle(
        with_tools=with_tools,
        plain=plain,
        primary_name=settings.openai_model_primary,
        fallback_name=settings.openai_model_fallback,
        mode="openai",
    )
