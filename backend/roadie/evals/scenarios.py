"""Cenários de avaliação.

Cada cenário fixa remetente e relógio, e cada turno declara o que se espera
da resposta: ferramentas que precisam ter sido chamadas, cláusulas citadas,
trechos que devem (ou não) aparecer no texto, ticket aberto ou não. As
expectativas de texto são tolerantes (qualquer um de vários trechos), porque
o modelo escreve livremente; o que não pode variar são as fontes consultadas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TUESDAY_10 = "2026-03-24T10:00:00"
SATURDAY_14 = "2026-03-28T14:00:00"
SUNDAY_11 = "2026-03-29T11:00:00"

CAMILA = "(67) 99567-8901"  # cliente 10: pedido 16 pendente (22/03)
UNKNOWN = "(67) 98888-7777"  # número fora do cadastro


@dataclass
class Turn:
    text: str
    expect_tools: list[str] = field(default_factory=list)
    expect_any: list[str] = field(default_factory=list)
    expect_none: list[str] = field(default_factory=list)
    expect_clauses: list[str] = field(default_factory=list)
    expect_ticket: bool | None = None
    note: str | None = None


@dataclass
class Scenario:
    slug: str
    title: str
    description: str
    sender_phone: str | None
    clock: str
    turns: list[Turn]
    nontrivial: bool = False


SCENARIOS: list[Scenario] = [
    Scenario(
        slug="catalogo-violoes",
        title="Catálogo: violões até R$ 1.000 e produto esgotado",
        description=(
            "Cliente sem cadastro pergunta por violões dentro de um orçamento, refina por tipo de corda e "
            "pede um modelo que está com estoque zero. O Tom precisa consultar o catálogo a cada pergunta, "
            "apresentar preço de tabela e PIX e oferecer alternativas em vez de confirmar disponibilidade."
        ),
        sender_phone=UNKNOWN,
        clock=TUESDAY_10,
        turns=[
            Turn(
                "Oi! Quais opções de violões vocês têm custando até R$ 1.000?",
                expect_tools=["buscar_produtos"],
                expect_any=["R$"],
            ),
            Turn(
                "E com cordas de aço, tem algum até esse valor?",
                expect_tools=["buscar_produtos"],
                expect_any=["aço", "aco"],
            ),
            Turn(
                "O Giannini GF-3D tá disponível pra entrega?",
                expect_tools=["detalhar_produto"],
                expect_any=[
                    "indispon",
                    "esgotad",
                    "temporariamente",
                    "sem estoque",
                    "fora de estoque",
                ],
                note="Produto ativo com estoque zero: o manual manda sugerir alternativas.",
            ),
        ],
    ),
    Scenario(
        slug="preco-parcelas-promocao",
        title="Preço, parcelamento e promoção sem acumular com PIX",
        description=(
            "Perguntas de preço que exigem as regras de pagamento: parcela mínima por faixa, promoção ativa "
            "apresentada com preço original e percentual, e o desconto de PIX que não se soma à promoção."
        ),
        sender_phone=UNKNOWN,
        clock=TUESDAY_10,
        turns=[
            Turn(
                "Quanto custa o Takamine GD20?",
                expect_tools=["detalhar_produto"],
                expect_any=["2.199"],
            ),
            Turn(
                "Consigo parcelar em 12x?",
                expect_any=["12x", "12 x", "183"],
                note="R$ 2.199 em 12x dá R$ 183,25, acima da parcela mínima de R$ 100.",
            ),
            Turn(
                "E o Taylor 110e, está em promoção?",
                expect_tools=["detalhar_produto"],
                expect_any=["5.519", "8%"],
                expect_clauses=["6.2"],
            ),
            Turn(
                "Se eu pagar o Taylor no PIX ganho mais 5% de desconto?",
                expect_any=[
                    "não acumul",
                    "nao acumul",
                    "não se aplica",
                    "não soma",
                    "não é cumulativ",
                    "já é promocional",
                    "já está",
                ],
                expect_none=["5.243"],
                note="Promoções não são cumulativas com o PIX (cláusula 6.2).",
            ),
        ],
    ),
    Scenario(
        slug="devolucao-pedido-pendente",
        title="Arrependimento em pedido ainda não enviado",
        description=(
            "Cliente identificada pelo telefone quer devolver uma compra. O Tom consulta os pedidos dela, "
            "aplica a política de trocas e descobre que o pedido ainda está pendente: o caminho é "
            "cancelamento, não devolução. Em seguida registra a solicitação com protocolo."
        ),
        sender_phone=CAMILA,
        clock=TUESDAY_10,
        nontrivial=True,
        turns=[
            Turn(
                "Me arrependi da minha compra, posso devolver meu pedido?",
                expect_tools=["meus_pedidos"],
                expect_any=["16", "pedido"],
                note="Com a cliente identificada, o Tom pode olhar os pedidos dela sem pedir dados.",
            ),
            Turn(
                "É esse mesmo, o pedido 16.",
                expect_tools=["avaliar_devolucao"],
                expect_any=["cancel"],
                expect_clauses=["4.1"],
            ),
            Turn(
                "Pode registrar o cancelamento pra mim, por favor.",
                expect_tools=["abrir_ticket"],
                expect_any=["RD-2026"],
                expect_ticket=True,
            ),
        ],
    ),
    Scenario(
        slug="pedido-atrasado-verificacao",
        title="Pedido atrasado com verificação de identidade",
        description=(
            "Número desconhecido pergunta por um pedido. O Tom não pode revelar nada antes de verificar a "
            "identidade com número do pedido e e-mail. Depois, descobre que o pedido está enviado e além da "
            "previsão de entrega, pede desculpas, informa o rastreio e abre um ticket de frete."
        ),
        sender_phone=UNKNOWN,
        clock=TUESDAY_10,
        nontrivial=True,
        turns=[
            Turn(
                "Oi, cadê meu pedido 8? Já devia ter chegado.",
                expect_any=["e-mail", "email", "telefone", "confirmar", "cadastro"],
                expect_none=["BRJL5544332BR"],
                note="Sem identidade verificada, nenhuma informação do pedido pode sair.",
            ),
            Turn(
                "O e-mail é anacarol.ferreira@coldmail.com",
                expect_tools=["verificar_identidade"],
                expect_any=["Ana", "BRJL5544332BR", "enviado", "atras"],
            ),
            Turn(
                "Então abre um chamado pra vocês verificarem com a transportadora.",
                expect_tools=["abrir_ticket"],
                expect_any=["RD-2026"],
                expect_ticket=True,
            ),
        ],
    ),
    Scenario(
        slug="fora-de-escopo-e-quarentena",
        title="Domingo: horário, acessórios, assunto alheio, categoria vazia e cadastro em quarentena",
        description=(
            "Com a loja fechada, o Tom informa quando reabre, recusa acessórios e assuntos fora da música, "
            "explica que a categoria de sopros existe mas está sem modelos, e trata um produto com cadastro "
            "contraditório sem afirmar preço."
        ),
        sender_phone=UNKNOWN,
        clock=SUNDAY_11,
        turns=[
            Turn(
                "Vocês estão abertos agora?",
                expect_tools=["horario_loja"],
                expect_any=["fechad"],
            ),
            Turn(
                "Vocês vendem cordas e cabos?",
                expect_any=[
                    "não vendemos",
                    "não trabalhamos",
                    "não comercializ",
                    "exclusivamente",
                    "só instrumentos",
                    "somente instrumentos",
                    "apenas instrumentos",
                ],
            ),
            Turn(
                "Beleza. Me diz uma coisa: qual a previsão do tempo pra amanhã em Campo Grande?",
                expect_any=["instrumento", "música", "musica", "loja"],
                expect_none=["graus", "°C", "chuva"],
            ),
            Turn(
                "Tem saxofone?",
                expect_tools=["buscar_produtos"],
                expect_any=[
                    "nenhum",
                    "não temos",
                    "sem modelo",
                    "no momento",
                    "não há",
                    "ainda não",
                ],
            ),
            Turn(
                "Quanto custa o Korg Synth 1 Pro?",
                expect_tools=["detalhar_produto"],
                expect_none=["1.127"],
                expect_any=["diverg", "confirmar", "cadastro", "equipe", "verificar"],
                note="Produto em quarentena: nome Korg, descrição Roland, specs e preço contraditórios.",
            ),
        ],
    ),
]


def find_scenario(slug: str) -> Scenario:
    for s in SCENARIOS:
        if s.slug == slug:
            return s
    raise KeyError(slug)
