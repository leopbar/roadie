"""Modelo simulado para testes e para rodar sem chave de API.

Não "entende" nada: reconhece padrões simples na última mensagem do cliente,
chama a ferramenta correspondente e, quando a ferramenta responde, devolve um
texto curto. Serve para testar o encanamento inteiro (grafo, ferramentas,
recibos, persistência, API) de forma determinística e sem custo.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

MONEY_RE = re.compile(r"R?\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:[.,]\d+)?)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ORDER_RE = re.compile(r"pedido\s*(?:n[ºo°]?\s*)?#?(\d+)", re.IGNORECASE)


def _money(text: str) -> float | None:
    m = re.search(r"(?:R\$|até|ate|por|de)\s*(\d[\d.]*)(?:,(\d{2}))?", text, re.IGNORECASE)
    if not m:
        return None
    inteiro = m.group(1).replace(".", "")
    return float(f"{inteiro}.{m.group(2) or '00'}")


class MockTom(BaseChatModel):
    """Chat model determinístico com chamadas de ferramenta roteirizadas."""

    model_name: str = "mock-tom"

    @property
    def _llm_type(self) -> str:
        return "mock-tom"

    def bind_tools(self, tools: Any, **kwargs: Any) -> MockTom:  # type: ignore[override]
        return self

    def with_fallbacks(self, fallbacks: Any, **kwargs: Any) -> MockTom:  # type: ignore[override]
        return self

    # ------------------------------------------------------------------ roteiro
    @staticmethod
    def _plan(text: str) -> tuple[str, dict] | None:
        t = text.lower()
        order = ORDER_RE.search(t)
        email = EMAIL_RE.search(text)
        if order and email:
            return "verificar_identidade", {
                "pedido_id": int(order.group(1)),
                "email": email.group(0),
            }
        if order and re.search(r"devolv|arrepend|troc|defeit", t):
            motivo = (
                "defeito"
                if "defeit" in t
                else ("preferencia" if "troc" in t and "cor" in t else "arrependimento")
            )
            return "avaliar_devolucao", {"pedido_id": int(order.group(1)), "motivo": motivo}
        if order:
            return "consultar_pedido", {"pedido_id": int(order.group(1))}
        if re.search(r"meus pedidos|minhas compras", t):
            return "meus_pedidos", {}
        if re.search(r"reclama|absurdo|problema com|quero falar com", t):
            return "abrir_ticket", {"categoria": "reclamacao", "resumo": text[:200]}
        if re.search(r"endere[cç]o|telefone|contato|cnpj|onde fica", t):
            return "informacoes_loja", {}
        if re.search(r"hor[aá]rio|aberta|aberto|fechad|que horas", t):
            return "horario_loja", {}
        if re.search(r"promo|oferta|desconto", t) and not re.search(r"quanto custa", t):
            return "promocoes_ativas", {}
        if re.search(r"frete|entrega", t):
            city = re.search(r"(?:para|em)\s+([A-ZÁ-Ú][\w]+(?:\s+[A-ZÁ-Ú][\w]+)*)", text)
            return "calcular_frete", {
                "cidade": city.group(1) if city else None,
                "valor_pedido": _money(text),
            }
        if re.search(r"parcel", t):
            return "calcular_parcelas", {"valor": _money(text) or 0}
        if re.search(r"quanto custa|pre[cç]o d[oa]|valor d[oa]", t):
            name = re.sub(
                r".*?(quanto custa|pre[cç]o d[oa]|valor d[oa])\s*(o|a|um|uma)?\s*", "", t
            ).strip(" ?.!")
            return "detalhar_produto", {"nome": name}
        if re.search(r"pol[ií]tica|garantia|devolu|troca|pagamento|cart[aã]o|boleto|pix\b", t):
            return "consultar_politicas", {"pergunta": text}
        if re.search(
            r"viol[aã]o|viol[oõ]es|ukulele|guitarra|baixo|bateria|teclado|piano|sax|flauta|trompete|violino",
            t,
        ):
            cordas = "aco" if re.search(r"a[cç]o", t) else ("nylon" if "nylon" in t else None)
            return "buscar_produtos", {"termo": text, "preco_max": _money(text), "cordas": cordas}
        return None

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        last = messages[-1]
        if isinstance(last, ToolMessage):
            tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
            names = ", ".join(dict.fromkeys(m.name or "ferramenta" for m in tool_msgs[-3:]))
            try:
                payload = json.loads(str(last.content))
            except json.JSONDecodeError:
                payload = {"bruto": str(last.content)[:200]}
            brief = json.dumps(payload, ensure_ascii=False)[:400]
            text = f"[simulado] Consultei {names} e aqui está o que encontrei: {brief}"
            return self._result(AIMessage(content=text))

        human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        plan = self._plan(str(human.content)) if human else None
        if plan is None:
            text = "[simulado] Oi! Aqui é o Tom, da Empório da Música. Posso ajudar com instrumentos, pedidos e políticas da loja. O que você precisa?"
            return self._result(AIMessage(content=text))
        name, args = plan
        call = {
            "name": name,
            "args": {k: v for k, v in args.items() if v is not None},
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "tool_call",
        }
        return self._result(AIMessage(content="", tool_calls=[call]))

    def _result(self, message: AIMessage) -> ChatResult:
        message.response_metadata = {"model_name": self.model_name}
        message.usage_metadata = {"input_tokens": 120, "output_tokens": 40, "total_tokens": 160}
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, None, **kwargs)
