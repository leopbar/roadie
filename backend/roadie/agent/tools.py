"""Ferramentas do Tom.

Cada ferramenta devolve dois valores: o conteúdo que o modelo lê (JSON em
português) e um artefato de evidência que não vai para o modelo, mas entra
no recibo da resposta: tabelas e linhas consultadas, cláusulas citadas,
regras aplicadas, mudanças de identidade e tickets abertos.

Regra de ouro: ferramentas de pedido só enxergam os pedidos do cliente
identificado na conversa. Isso é imposto aqui, não no prompt.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from time import perf_counter

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from sqlalchemy import func, select

from roadie.agent import catalog
from roadie.agent.context import RunContext, ctx_from_config
from roadie.db.models import Customer, PolicyClause, Ticket, TicketCategory
from roadie.ingest.csv_loader import only_digits
from roadie.policy import rules
from roadie.policy.search import search_clauses
from roadie.textfmt import brl

MAX_IDENTITY_ATTEMPTS = 3
TICKET_CATEGORY_ALIASES = {
    "reclamacao": TicketCategory.reclamacao,
    "reclamação": TicketCategory.reclamacao,
    "cancelamento": TicketCategory.cancelamento,
    "devolucao": TicketCategory.devolucao,
    "devolução": TicketCategory.devolucao,
    "troca": TicketCategory.troca,
    "frete": TicketCategory.frete,
    "cadastro": TicketCategory.cadastro,
    "garantia": TicketCategory.garantia,
    "outro": TicketCategory.outro,
}


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _evidence(
    tool_name: str,
    *,
    summary: str,
    started: float,
    tables: list[str] | None = None,
    rows: list[tuple[str, object]] | None = None,
    clauses: list[str] | None = None,
    rules_used: list[str] | None = None,
    flags: list[str] | None = None,
    identity_update: dict | None = None,
    ticket: dict | None = None,
    ok: bool = True,
) -> dict:
    return {
        "tool": tool_name,
        "ok": ok,
        "summary": summary,
        "duration_ms": round((perf_counter() - started) * 1000, 1),
        "tables": tables or [],
        "rows": [{"table": t, "id": i} for t, i in (rows or [])],
        "clauses": clauses or [],
        "rules": rules_used or [],
        "flags": flags or [],
        "identity_update": identity_update,
        "ticket": ticket,
    }


def _mask_phone(digits: str | None) -> str | None:
    return f"***{digits[-4:]}" if digits and len(digits) >= 4 else None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _identity_required(ctx: RunContext) -> dict | None:
    if ctx.identity.verified and ctx.identity.customer_id:
        return None
    return {
        "erro": "identidade_nao_verificada",
        "instrucao": (
            "O cliente ainda não foi identificado. Peça o número do pedido e o e-mail (ou o telefone) "
            "do cadastro e chame verificar_identidade antes de falar de qualquer pedido."
        ),
    }


def _quarantine_flags(products) -> list[str]:
    out = []
    for p in products:
        notice = catalog.quality_notice(p)
        if notice and notice["nivel"] == "quarentena":
            out.append(f"product:{p.product_id}:quarentena")
    return out


# ----------------------------------------------------------------------------
# Catálogo
# ----------------------------------------------------------------------------
@tool("buscar_produtos", response_format="content_and_artifact", parse_docstring=True)
async def buscar_produtos(
    termo: str | None = None,
    categoria: str | None = None,
    preco_max: float | None = None,
    preco_min: float | None = None,
    cordas: str | None = None,
    eletronica: bool | None = None,
    apenas_disponiveis: bool = True,
    config: RunnableConfig = None,
) -> tuple[str, dict]:
    """Busca instrumentos no catálogo por termo, categoria, faixa de preço e características.

    Use para perguntas como "quais violões até R$ 1000", "tem ukulele tenor", "guitarra Fender".
    Retorna até 8 produtos com preço de tabela, preço no PIX, promoção ativa e disponibilidade.

    Args:
        termo: Palavras do nome, marca ou modelo (ex.: "Takamine GD20", "ukulele tenor"). Opcional.
        categoria: Categoria em português (violões, guitarras, baixos, baterias, teclados, sopros, cordas orquestrais, ukuleles). Opcional.
        preco_max: Preço máximo em reais, já considerando promoções ativas. Opcional.
        preco_min: Preço mínimo em reais. Opcional.
        cordas: Tipo de cordas para violões e ukuleles: "nylon" ou "aco". Opcional.
        eletronica: True para só eletroacústicos (com captação), False para só acústicos. Opcional.
        apenas_disponiveis: Se True (padrão), só produtos ativos com estoque. Use False para checar itens esgotados ou descontinuados.
    """
    ctx = ctx_from_config(config)
    started = perf_counter()
    cat_ids = catalog.resolve_category_ids(categoria) if categoria else []
    term_cat_ids, terms = catalog.split_terms(termo)
    if not cat_ids:
        cat_ids = term_cat_ids
    pmax = Decimal(str(preco_max)) if preco_max is not None else None
    pmin = Decimal(str(preco_min)) if preco_min is not None else None

    async with ctx.session_factory() as session:
        kwargs = dict(
            terms=terms,
            category_ids=cat_ids,
            preco_min=pmin,
            preco_max=pmax,
            cordas=cordas,
            eletronica=eletronica,
        )
        products = await catalog.search_products(
            session, apenas_disponiveis=apenas_disponiveis, **kwargs
        )
        relaxed = False
        if not products and apenas_disponiveis:
            products = await catalog.search_products(session, apenas_disponiveis=False, **kwargs)
            relaxed = bool(products)
        empty = [] if products else await catalog.empty_category_names(session, cat_ids)
        cards = [catalog.product_card(p) for p in products]

    content: dict = {"total": len(cards), "produtos": cards}
    if relaxed:
        content["observacao"] = (
            "Nenhum produto disponível com esses filtros; os listados estão esgotados, descontinuados ou em pré-venda. "
            "Ofereça alternativas parecidas (busque sem o termo exato ou com faixa de preço)."
        )
    elif empty:
        content["observacao"] = (
            f"A loja tem a categoria {', '.join(empty)} no catálogo, mas não há nenhum modelo cadastrado no momento. "
            "Diga isso com transparência e ofereça registrar o interesse do cliente num ticket."
        )
    elif not cards:
        content["observacao"] = (
            "Nada encontrado. Tente outro termo, ou só a categoria, ou uma faixa de preço maior."
        )

    artifact = _evidence(
        "buscar_produtos",
        summary=f"{len(cards)} produto(s)" + (" (sem disponíveis)" if relaxed else ""),
        started=started,
        tables=["products", "promotions", "categories"],
        rows=[("products", p.product_id) for p in products],
        clauses=["3"] + (["6.2"] if any(c.get("promocao") for c in cards) else []),
        rules_used=["quote_price"],
        flags=_quarantine_flags(products),
    )
    return _json(content), artifact


@tool("detalhar_produto", response_format="content_and_artifact", parse_docstring=True)
async def detalhar_produto(
    produto_id: int | None = None,
    nome: str | None = None,
    config: RunnableConfig = None,
) -> tuple[str, dict]:
    """Traz os detalhes de um produto: descrição, especificações, preço, promoção, parcelamento e alternativas.

    Use quando o cliente perguntar o preço ou os detalhes de um modelo específico ("quanto custa o Takamine GD20?").
    Se o produto estiver indisponível ou com cadastro em quarentena, vêm alternativas disponíveis.

    Args:
        produto_id: Id do produto, quando já conhecido de uma busca anterior. Opcional.
        nome: Nome ou modelo aproximado do produto (ex.: "Takamine GD20"). Opcional.
    """
    ctx = ctx_from_config(config)
    started = perf_counter()
    async with ctx.session_factory() as session:
        p = await catalog.find_product(session, produto_id, nome)
        if p is None:
            content = {
                "erro": "produto_nao_encontrado",
                "instrucao": "Peça mais detalhes do modelo ou faça uma busca por categoria.",
            }
            return _json(content), _evidence(
                "detalhar_produto",
                summary="não encontrado",
                started=started,
                tables=["products"],
                ok=False,
            )
        code, _ = catalog.availability(p)
        notice = catalog.quality_notice(p)
        alts = (
            await catalog.alternatives_for(session, p)
            if (code != "disponivel" or (notice and notice["nivel"] == "quarentena"))
            else []
        )
        detail = catalog.product_detail(p, alts)

    quote = catalog.price_quote(p)
    artifact = _evidence(
        "detalhar_produto",
        summary=f"{p.name} ({detail['disponibilidade']})",
        started=started,
        tables=["products", "promotions", "categories"],
        rows=[("products", p.product_id)] + [("products", a.product_id) for a in alts],
        clauses=quote.clauses + ["3.1"],
        rules_used=["quote_price", "installment_plan"],
        flags=_quarantine_flags([p]),
    )
    return _json(detail), artifact


@tool("promocoes_ativas", response_format="content_and_artifact")
async def promocoes_ativas(config: RunnableConfig = None) -> tuple[str, dict]:
    """Lista as promoções ativas agora, com preço original, percentual e preço promocional.

    Use quando o cliente perguntar por ofertas, descontos ou promoções em geral.
    Promoções com is_active falso não aparecem: nunca prometa uma promoção expirada.
    """
    ctx = ctx_from_config(config)
    started = perf_counter()
    async with ctx.session_factory() as session:
        products = await catalog.active_promotions(session)
        cards = [catalog.product_card(p) for p in products]
    content = {
        "total": len(cards),
        "promocoes": cards,
        "regra": "Promoções não são cumulativas com o desconto de PIX.",
    }
    artifact = _evidence(
        "promocoes_ativas",
        summary=f"{len(cards)} promoção(ões) ativa(s)",
        started=started,
        tables=["promotions", "products"],
        rows=[("products", p.product_id) for p in products],
        clauses=["6.1", "6.2"],
        rules_used=["quote_price"],
    )
    return _json(content), artifact


# ----------------------------------------------------------------------------
# Identidade e pedidos
# ----------------------------------------------------------------------------
@tool("verificar_identidade", response_format="content_and_artifact", parse_docstring=True)
async def verificar_identidade(
    pedido_id: int,
    email: str | None = None,
    telefone: str | None = None,
    config: RunnableConfig = None,
) -> tuple[str, dict]:
    """Confirma a identidade do cliente cruzando o número do pedido com o e-mail ou telefone do cadastro.

    Obrigatório antes de falar de pedidos quando o remetente não está identificado.
    Nunca diga ao cliente qual e-mail ou telefone está no cadastro.

    Args:
        pedido_id: Número do pedido informado pelo cliente.
        email: E-mail informado pelo cliente. Opcional.
        telefone: Telefone informado pelo cliente. Opcional.
    """
    ctx = ctx_from_config(config)
    started = perf_counter()
    if ctx.identity.attempts >= MAX_IDENTITY_ATTEMPTS:
        content = {
            "verificado": False,
            "erro": "limite_de_tentativas",
            "instrucao": "Não tente de novo. Oriente o cliente a falar com a equipe humana e ofereça abrir um ticket de cadastro.",
        }
        return _json(content), _evidence(
            "verificar_identidade", summary="limite de tentativas", started=started, ok=False
        )

    async with ctx.session_factory() as session:
        order = await catalog.get_order(session, pedido_id)
    ok = False
    if order and order.customer:
        c = order.customer
        if email and c.email and email.strip().lower() == c.email.lower():
            ok, via = True, "pedido+email"
        elif (
            telefone
            and c.phone_digits
            and only_digits(telefone)[-8:] == c.phone_digits[-8:]
            and len(only_digits(telefone)) >= 8
        ):
            ok, via = True, "pedido+telefone"
    if ok:
        ctx.identity.customer_id = order.customer_id
        ctx.identity.name = order.customer.name
        ctx.identity.city = order.customer.city
        ctx.identity.verified = True
        ctx.identity.via = via
        ctx.identity_changed = True
        content = {
            "verificado": True,
            "cliente": ctx.identity.first_name,
            "cidade": ctx.identity.city,
        }
        return _json(content), _evidence(
            "verificar_identidade",
            summary=f"identificado ({via})",
            started=started,
            tables=["orders", "customers"],
            rows=[("orders", order.order_id), ("customers", order.customer_id)],
            clauses=["9"],
            identity_update=ctx.identity.as_dict(),
        )
    ctx.identity.attempts += 1
    left = MAX_IDENTITY_ATTEMPTS - ctx.identity.attempts
    content = {
        "verificado": False,
        "motivo": "os dados informados não conferem com o pedido",
        "tentativas_restantes": left,
        "instrucao": "Peça para conferir o número do pedido e o e-mail/telefone. Não revele nenhum dado do cadastro.",
    }
    return _json(content), _evidence(
        "verificar_identidade",
        summary="dados não conferem",
        started=started,
        tables=["orders", "customers"],
        clauses=["9"],
        ok=False,
    )


@tool("meus_pedidos", response_format="content_and_artifact")
async def meus_pedidos(config: RunnableConfig = None) -> tuple[str, dict]:
    """Lista os pedidos do cliente identificado nesta conversa, do mais recente ao mais antigo.

    Só funciona com o cliente identificado (pelo telefone do remetente ou por verificar_identidade).
    """
    ctx = ctx_from_config(config)
    started = perf_counter()
    if err := _identity_required(ctx):
        return _json(err), _evidence(
            "meus_pedidos",
            summary="identidade não verificada",
            started=started,
            ok=False,
            clauses=["9"],
        )
    async with ctx.session_factory() as session:
        orders = await catalog.orders_for_customer(session, ctx.identity.customer_id)  # type: ignore[arg-type]
    today = ctx.now.date()
    content = {
        "cliente": ctx.identity.first_name,
        "total": len(orders),
        "pedidos": [catalog.order_summary(o, today) for o in orders],
    }
    return _json(content), _evidence(
        "meus_pedidos",
        summary=f"{len(orders)} pedido(s)",
        started=started,
        tables=["orders", "order_items", "products"],
        rows=[("orders", o.order_id) for o in orders],
        rules_used=["delivery_status"],
        clauses=["5.3", "9"],
    )


@tool("consultar_pedido", response_format="content_and_artifact", parse_docstring=True)
async def consultar_pedido(pedido_id: int, config: RunnableConfig = None) -> tuple[str, dict]:
    """Consulta status, itens, pagamento, rastreio e situação de entrega de um pedido do cliente identificado.

    Se o pedido não for do cliente identificado, a ferramenta não revela nada.

    Args:
        pedido_id: Número do pedido.
    """
    ctx = ctx_from_config(config)
    started = perf_counter()
    if err := _identity_required(ctx):
        return _json(err), _evidence(
            "consultar_pedido",
            summary="identidade não verificada",
            started=started,
            ok=False,
            clauses=["9"],
        )
    async with ctx.session_factory() as session:
        order = await catalog.get_order(session, pedido_id)
    if order is None or order.customer_id != ctx.identity.customer_id:
        content = {
            "erro": "pedido_nao_encontrado_para_este_cliente",
            "instrucao": "Diga que não encontrou esse pedido no cadastro do cliente e peça para conferir o número.",
        }
        return _json(content), _evidence(
            "consultar_pedido",
            summary="não encontrado para o cliente",
            started=started,
            ok=False,
            tables=["orders"],
            clauses=["9"],
        )
    summary = catalog.order_summary(order, ctx.now.date())
    if summary.get("atrasado"):
        summary["instrucao"] = (
            "Pedido além da previsão: peça desculpas, informe o código de rastreio e ofereça abrir um ticket de frete para a equipe acompanhar."
        )
    return _json(summary), _evidence(
        "consultar_pedido",
        summary=f"pedido {order.order_id}: {summary['status']}",
        started=started,
        tables=["orders", "order_items", "products"],
        rows=[("orders", order.order_id)],
        rules_used=["delivery_status", "tracking_is_valid"],
        clauses=["5.1", "5.2", "5.3"],
        flags=[f"order:{order.order_id}:{f['flag']}" for f in (order.quality_flags or [])],
    )


@tool("avaliar_devolucao", response_format="content_and_artifact", parse_docstring=True)
async def avaliar_devolucao(
    pedido_id: int,
    motivo: str,
    data_recebimento: str | None = None,
    config: RunnableConfig = None,
) -> tuple[str, dict]:
    """Avalia se um pedido pode ser devolvido ou trocado, aplicando os prazos da política de trocas.

    Motivos: "arrependimento" (desistência em até 7 dias do recebimento), "defeito" (30 dias da compra,
    depois garantia) ou "preferencia" (cor/modelo, 7 dias). Pedidos ainda não enviados viram cancelamento.
    Precisa do cliente identificado.

    Args:
        pedido_id: Número do pedido.
        motivo: "arrependimento", "defeito" ou "preferencia".
        data_recebimento: Data em que o cliente recebeu o produto (dd/mm/aaaa), se ele informou. Opcional.
    """
    ctx = ctx_from_config(config)
    started = perf_counter()
    if err := _identity_required(ctx):
        return _json(err), _evidence(
            "avaliar_devolucao",
            summary="identidade não verificada",
            started=started,
            ok=False,
            clauses=["9"],
        )
    motivo_norm = catalog.normalize(motivo)
    if motivo_norm not in ("arrependimento", "defeito", "preferencia"):
        content = {
            "erro": "motivo_invalido",
            "instrucao": "Use arrependimento, defeito ou preferencia.",
        }
        return _json(content), _evidence(
            "avaliar_devolucao", summary="motivo inválido", started=started, ok=False
        )
    async with ctx.session_factory() as session:
        order = await catalog.get_order(session, pedido_id)
    if order is None or order.customer_id != ctx.identity.customer_id:
        content = {
            "erro": "pedido_nao_encontrado_para_este_cliente",
            "instrucao": "Peça para conferir o número do pedido.",
        }
        return _json(content), _evidence(
            "avaliar_devolucao",
            summary="não encontrado para o cliente",
            started=started,
            ok=False,
            clauses=["9"],
        )
    verdict = rules.return_eligibility(
        order.status.value,
        order.order_date,
        order.estimated_delivery,
        motivo_norm,
        ctx.now.date(),
        _parse_date(data_recebimento),
    )
    content = {
        "pedido": catalog.order_summary(order, ctx.now.date()),
        "avaliacao": verdict.as_dict(),
    }
    if verdict.eligible is None:
        content["instrucao"] = (
            "Pergunte ao cliente se já recebeu o produto e em que data, e chame de novo com data_recebimento."
        )
    elif (
        verdict.path
        in (
            "cancelamento_antes_envio",
            "devolucao_arrependimento",
            "troca_defeito",
            "troca_preferencia",
        )
        and verdict.eligible
    ):
        content["instrucao"] = (
            "Explique as condições e ofereça registrar a solicitação com abrir_ticket (categoria devolucao, troca ou cancelamento)."
        )
    return _json(content), _evidence(
        "avaliar_devolucao",
        summary=f"{verdict.path}: {'elegível' if verdict.eligible else 'não elegível' if verdict.eligible is False else 'falta informação'}",
        started=started,
        tables=["orders", "order_items"],
        rows=[("orders", order.order_id)],
        rules_used=["return_eligibility"],
        clauses=verdict.clauses,
    )


# ----------------------------------------------------------------------------
# Regras: pagamento, frete, horário, informações
# ----------------------------------------------------------------------------
@tool("calcular_parcelas", response_format="content_and_artifact", parse_docstring=True)
async def calcular_parcelas(valor: float, config: RunnableConfig = None) -> tuple[str, dict]:
    """Calcula as opções de parcelamento sem juros para um valor, respeitando as parcelas mínimas da loja.

    Args:
        valor: Valor total em reais.
    """
    started = perf_counter()
    plan = rules.installment_plan(Decimal(str(valor)))
    d = plan.as_dict()
    d["options"] = [o for o in d["options"] if o["allowed"]]
    return _json(d), _evidence(
        "calcular_parcelas",
        summary=f"até {plan.max_installments}x para {brl(plan.total)}",
        started=started,
        rules_used=["installment_plan"],
        clauses=plan.clauses,
    )


@tool("calcular_frete", response_format="content_and_artifact", parse_docstring=True)
async def calcular_frete(
    cidade: str | None = None,
    valor_pedido: float | None = None,
    item_grande: bool = False,
    config: RunnableConfig = None,
) -> tuple[str, dict]:
    """Informa frete e prazo de entrega: grátis acima de R$ 500 na região de Campo Grande, Correios/Jadlog para outras cidades.

    Args:
        cidade: Cidade de entrega. Se omitida, usa a cidade do cliente identificado. Opcional.
        valor_pedido: Valor do pedido em reais, para a regra do frete grátis. Opcional.
        item_grande: True para bateria acústica, piano digital ou contrabaixo (frete especial). Opcional.
    """
    ctx = ctx_from_config(config)
    started = perf_counter()
    city = cidade or ctx.identity.city
    verdict = rules.shipping_for(
        city, Decimal(str(valor_pedido)) if valor_pedido is not None else None, item_grande
    )
    d = verdict.as_dict()
    if cidade is None and ctx.identity.city:
        d["observacao"] = f"Cidade usada: {ctx.identity.city} (cadastro do cliente)."
    return _json(d), _evidence(
        "calcular_frete",
        summary=f"{verdict.region}: {verdict.deadline or 'cotação'}",
        started=started,
        rules_used=["shipping_for"],
        clauses=verdict.clauses,
    )


@tool("horario_loja", response_format="content_and_artifact")
async def horario_loja(config: RunnableConfig = None) -> tuple[str, dict]:
    """Informa se a loja está aberta agora, quando fecha ou reabre, e a grade de horários da semana."""
    ctx = ctx_from_config(config)
    started = perf_counter()
    verdict = rules.store_hours(ctx.now)
    d = verdict.as_dict()
    d["observacao"] = (
        "Em datas especiais (Black Friday, aniversário da loja, Natal) o horário pode ser estendido, com aviso prévio."
    )
    return _json(d), _evidence(
        "horario_loja",
        summary="aberta" if verdict.is_open else "fechada",
        started=started,
        rules_used=["store_hours"],
        clauses=["2"],
    )


@tool("informacoes_loja", response_format="content_and_artifact")
async def informacoes_loja(config: RunnableConfig = None) -> tuple[str, dict]:
    """Dados da loja: endereço, telefone, WhatsApp, e-mail, CNPJ, história e o que ela vende (só instrumentos)."""
    ctx = ctx_from_config(config)
    started = perf_counter()
    async with ctx.session_factory() as session:
        stmt = (
            select(PolicyClause)
            .where(PolicyClause.clause_id.in_(["0", "1", "1.2", "7"]))
            .order_by(PolicyClause.order_index)
        )
        clauses = list((await session.scalars(stmt)).all())
    hours = rules.store_hours(ctx.now)
    content = {
        "ficha": {c.clause_id: {"titulo": c.title, "texto": c.body} for c in clauses},
        "horario": hours.schedule,
        "agora": hours.message,
        "observacao": (
            "O manual traz dois números: (67) 3341-4444 na ficha da empresa (telefone/WhatsApp) e "
            "(67) 3321-4500 como canal de atendimento por WhatsApp. Informe os dois com essa distinção."
        ),
    }
    return _json(content), _evidence(
        "informacoes_loja",
        summary="ficha da loja",
        started=started,
        tables=["policy_clauses"],
        clauses=["0", "1", "1.2", "2", "7"],
        rules_used=["store_hours"],
    )


@tool("consultar_politicas", response_format="content_and_artifact", parse_docstring=True)
async def consultar_politicas(pergunta: str, config: RunnableConfig = None) -> tuple[str, dict]:
    """Busca no manual de políticas da loja as cláusulas que respondem a uma dúvida (troca, devolução, garantia, frete, pagamento, promoções, privacidade).

    Devolve até 5 cláusulas com id, título e texto. Use o texto para explicar a regra em palavras simples.

    Args:
        pergunta: A dúvida do cliente ou palavras-chave (ex.: "troca por defeito", "garantia", "frete outras cidades").
    """
    ctx = ctx_from_config(config)
    started = perf_counter()
    async with ctx.session_factory() as session:
        hits = await search_clauses(session, pergunta)
    if not hits:
        content = {
            "total": 0,
            "sumario": [{"id": cid, "titulo": title} for cid, title in ctx.policy_toc],
            "instrucao": "Nada encontrado com esses termos. Tente palavras-chave do sumário acima.",
        }
        return _json(content), _evidence(
            "consultar_politicas",
            summary="sem resultados",
            started=started,
            tables=["policy_clauses"],
            ok=False,
        )
    content = {
        "total": len(hits),
        "clausulas": [{"id": h["id"], "titulo": h["titulo"], "texto": h["texto"]} for h in hits],
    }
    return _json(content), _evidence(
        "consultar_politicas",
        summary=", ".join(h["id"] for h in hits),
        started=started,
        tables=["policy_clauses"],
        rows=[("policy_clauses", h["id"]) for h in hits],
        clauses=[h["id"] for h in hits],
    )


# ----------------------------------------------------------------------------
# Tickets (passagem para a equipe humana)
# ----------------------------------------------------------------------------
@tool("abrir_ticket", response_format="content_and_artifact", parse_docstring=True)
async def abrir_ticket(
    categoria: str,
    resumo: str,
    pedido_id: int | None = None,
    config: RunnableConfig = None,
) -> tuple[str, dict]:
    """Registra uma solicitação para a equipe humana e devolve o protocolo e o prazo de retorno (24 horas úteis).

    Use para reclamações, cancelamentos, devoluções/trocas aprovadas, cotações de frete, divergências de cadastro,
    garantia e qualquer caso que o manual mande consultar a gerência.

    Args:
        categoria: Uma de: reclamacao, cancelamento, devolucao, troca, frete, cadastro, garantia, outro.
        resumo: Resumo objetivo do caso, com o que o cliente pediu e o contexto relevante.
        pedido_id: Número do pedido relacionado, se houver. Opcional.
    """
    ctx = ctx_from_config(config)
    started = perf_counter()
    category = TICKET_CATEGORY_ALIASES.get(catalog.normalize(categoria), TicketCategory.outro)
    sla = rules.complaint_sla(ctx.now)
    async with ctx.session_factory() as session:
        year = ctx.now.year
        count = await session.scalar(
            select(func.count(Ticket.id)).where(Ticket.protocol.like(f"RD-{year}-%"))
        )
        protocol = f"RD-{year}-{(count or 0) + 1:04d}"
        customer_id = ctx.identity.customer_id if ctx.identity.verified else None
        if customer_id is None and ctx.sender_phone_digits:
            customer_id = await session.scalar(
                select(Customer.customer_id).where(Customer.phone_digits == ctx.sender_phone_digits)
            )
        ticket = Ticket(
            protocol=protocol,
            conversation_id=ctx.conversation_id,
            customer_id=customer_id,
            order_id=pedido_id,
            category=category,
            summary=resumo.strip()[:2000],
            sla_due_at=sla.due_at,
        )
        session.add(ticket)
        await session.commit()
    info = {
        "protocolo": protocol,
        "categoria": category.value,
        "prazo_retorno": sla.message,
        "remetente": _mask_phone(ctx.sender_phone_digits),
    }
    ctx.tickets.append(info)
    return _json(info), _evidence(
        "abrir_ticket",
        summary=f"ticket {protocol} ({category.value})",
        started=started,
        tables=["tickets"],
        rows=[("tickets", protocol)],
        rules_used=["complaint_sla"],
        clauses=["7.3", "10"],
        ticket=info,
    )


ALL_TOOLS = [
    buscar_produtos,
    detalhar_produto,
    promocoes_ativas,
    verificar_identidade,
    meus_pedidos,
    consultar_pedido,
    avaliar_devolucao,
    calcular_parcelas,
    calcular_frete,
    horario_loja,
    informacoes_loja,
    consultar_politicas,
    abrir_ticket,
]
