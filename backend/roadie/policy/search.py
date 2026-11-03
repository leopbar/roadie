"""Busca textual nas cláusulas do manual (PostgreSQL full-text search em português).

Compartilhada pela ferramenta consultar_politicas do agente e pela API do
console, para que os dois vejam exatamente as mesmas cláusulas.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from roadie.db.models import PolicyClause

STOPWORDS = {
    "a",
    "o",
    "e",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "em",
    "um",
    "uma",
    "que",
    "com",
    "sem",
    "para",
    "por",
    "se",
    "meu",
    "minha",
    "meus",
    "minhas",
    "posso",
    "pode",
    "como",
    "qual",
    "quais",
    "tem",
    "tenho",
    "eu",
    "voce",
    "voces",
    "sobre",
    "ate",
    "ja",
    "nao",
    "mais",
    "muito",
    "ser",
    "esta",
    "estao",
    "foi",
    "sao",
    "quero",
    "queria",
    "gostaria",
    "preciso",
    "sua",
    "seu",
    "suas",
    "seus",
    "isso",
    "esse",
    "essa",
    "este",
    "pra",
    "ola",
    "oi",
}

_SQL = text(
    """
    WITH q AS (SELECT websearch_to_tsquery('portuguese', :q) AS tsq),
    docs AS (
        SELECT c.clause_id, c.title, c.body, c.order_index,
               setweight(to_tsvector('portuguese', unaccent(c.title)), 'A')
               || setweight(to_tsvector('portuguese', unaccent(c.body)), 'B') AS tsv
        FROM policy_clauses c
        WHERE c.clause_id <> '0'
    )
    SELECT d.clause_id, d.title, d.body, ts_rank(d.tsv, q.tsq) AS rank
    FROM docs d, q
    WHERE d.tsv @@ q.tsq
    ORDER BY rank DESC, d.order_index
    LIMIT :limit
    """
)


def normalize(text_: str | None) -> str:
    s = unicodedata.normalize("NFD", (text_ or "").lower().strip())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def keywords(question: str) -> list[str]:
    words = [
        w for w in re.findall(r"\w+", normalize(question)) if len(w) >= 3 and w not in STOPWORDS
    ]
    return list(dict.fromkeys(words))


async def search_clauses(session: AsyncSession, question: str, limit: int = 4) -> list[dict]:
    """Cláusulas mais relevantes para a pergunta, com seções-mãe expandidas nas filhas."""
    words = keywords(question)
    query = " OR ".join(words) if words else normalize(question)
    if not query:
        return []
    rows = (await session.execute(_SQL, {"q": query, "limit": limit})).all()

    expanded: list[dict] = []
    seen: set[str] = set()
    for clause_id, title, body, rank in rows:
        if "." not in clause_id:
            kids_stmt = (
                select(PolicyClause)
                .where(PolicyClause.section == int(clause_id), PolicyClause.clause_id != clause_id)
                .order_by(PolicyClause.order_index)
            )
            kids = list((await session.scalars(kids_stmt)).all())
            if kids:
                for k in kids:
                    if k.clause_id not in seen:
                        expanded.append(
                            {
                                "id": k.clause_id,
                                "titulo": k.title,
                                "texto": k.body,
                                "rank": float(rank),
                            }
                        )
                        seen.add(k.clause_id)
                continue
        if clause_id not in seen:
            expanded.append({"id": clause_id, "titulo": title, "texto": body, "rank": float(rank)})
            seen.add(clause_id)

    if not expanded and words:
        like_stmt = (
            select(PolicyClause)
            .where(
                PolicyClause.clause_id != "0",
                func.unaccent(func.lower(PolicyClause.title + " " + PolicyClause.body)).like(
                    f"%{words[0]}%"
                ),
            )
            .order_by(PolicyClause.order_index)
            .limit(limit)
        )
        expanded = [
            {"id": c.clause_id, "titulo": c.title, "texto": c.body, "rank": 0.0}
            for c in (await session.scalars(like_stmt)).all()
        ]
    return expanded[: limit + 1]


async def all_clauses(session: AsyncSession) -> list[PolicyClause]:
    stmt = select(PolicyClause).order_by(PolicyClause.order_index)
    return list((await session.scalars(stmt)).all())
