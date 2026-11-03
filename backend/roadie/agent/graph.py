"""Grafo de execução do Tom (LangGraph).

    START -> tom -> (tem chamadas de ferramenta?) -> ferramentas -> tom -> ... -> END

O nó "tom" monta o prompt de sistema a partir do contexto da rodada (relógio,
identidade, sumário do manual) e chama o modelo. O nó "ferramentas" executa
as chamadas. Um limite de rodadas evita laços infinitos: ao atingi-lo, o
modelo responde sem ferramentas e oferece a passagem para a equipe.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from roadie.agent.context import ctx_from_config
from roadie.agent.llm import ModelBundle
from roadie.agent.persona import build_system_prompt

LIMIT_NOTE = (
    "Você atingiu o limite de consultas para esta mensagem. Responda agora com o que já apurou, "
    "sem chamar ferramentas, e ofereça registrar um ticket para a equipe concluir o atendimento."
)


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    rounds: int


def build_graph(models: ModelBundle, tools: list, max_tool_rounds: int):
    async def tom(state: AgentState, config: RunnableConfig) -> dict:
        ctx = ctx_from_config(config)
        rounds = state.get("rounds", 0)
        system = SystemMessage(content=build_system_prompt(ctx))
        messages = [system, *state["messages"]]
        if rounds >= max_tool_rounds:
            messages.append(SystemMessage(content=LIMIT_NOTE))
            response = await models.plain.ainvoke(messages, config)
            if isinstance(response, AIMessage) and response.tool_calls:
                response = AIMessage(
                    content=str(response.content)
                    or "Vou pedir para a equipe concluir esse atendimento, tudo bem?"
                )
        else:
            response = await models.with_tools.ainvoke(messages, config)
        return {"messages": [response], "rounds": rounds + 1}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "ferramentas"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("tom", tom)
    graph.add_node("ferramentas", ToolNode(tools))
    graph.add_edge(START, "tom")
    graph.add_conditional_edges("tom", route, {"ferramentas": "ferramentas", END: END})
    graph.add_edge("ferramentas", "tom")
    return graph.compile()
