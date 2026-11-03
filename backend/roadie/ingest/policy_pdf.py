"""Extração do manual de políticas (PDF) em cláusulas numeradas.

O manual é curto (8 páginas) e bem estruturado em seções "N." e "N.N".
Em vez de picar o texto em pedaços de tamanho fixo, a ingestão respeita a
numeração do próprio documento: cada seção vira uma cláusula com id ("4.1"),
título e corpo. O agente cita esses ids, e o motor de regras aponta para eles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

HEADER_RE = re.compile(
    r"^Emp[óo]rio da M[úu]sica\s+Manual de Pol[íi]ticas e Procedimentos\s*$", re.IGNORECASE
)
FOOTER_RE = re.compile(r"^P[áa]gina\s+\d+\s*$", re.IGNORECASE)
SECTION_RE = re.compile(r"^(\d{1,2})\.\s+(\S.*?)\s*$")
SUBSECTION_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\s+(\S.*?)\s*$")
BULLET = "•"


@dataclass
class ClauseDraft:
    clause_id: str
    section: int
    title: str
    page: int
    order_index: int
    lines: list[str] = field(default_factory=list)

    children: list[ClauseDraft] = field(default_factory=list)

    @property
    def body(self) -> str:
        merged: list[str] = []
        pending_bullet = False
        for line in self.lines:
            if line == BULLET:
                pending_bullet = True
                continue
            if pending_bullet:
                merged.append(f"{BULLET} {line}")
                pending_bullet = False
            elif merged and _should_join(merged[-1], line):
                merged[-1] = f"{merged[-1]} {line}"
            else:
                merged.append(line)
        text = "\n".join(merged).strip()
        if not text and self.children:
            titles = ", ".join(f"{c.clause_id} {c.title}" for c in self.children)
            text = f"Seção com as subseções: {titles}."
        return text


_SENTENCE_END = (".", ":", ";", "!", "?")


def _should_join(prev: str, line: str) -> bool:
    """O PDF quebra linhas no meio das frases; junta quando a continuação é evidente."""
    if prev.endswith(_SENTENCE_END) or line.startswith(BULLET):
        return False
    first = line[0]
    return first.islower() or first.isdigit() or first in "(%"


def clean_line(raw: str) -> str:
    return raw.replace("​", "").replace("\xa0", " ").strip()


def extract_pages(pdf_path: Path) -> list[str]:
    with pymupdf.open(pdf_path) as doc:
        return [page.get_text() for page in doc]


def parse_clauses(pages: list[str]) -> list[ClauseDraft]:
    """Divide o texto em cláusulas seguindo a numeração do manual."""
    clauses: list[ClauseDraft] = []
    current: ClauseDraft | None = None
    expected_section = 1
    current_section = 0
    last_sub = 0
    order = 0
    section_clause: ClauseDraft | None = None

    def start(clause_id: str, section: int, title: str, page: int) -> ClauseDraft:
        nonlocal order, current, section_clause
        order += 1
        current = ClauseDraft(
            clause_id=clause_id, section=section, title=title, page=page, order_index=order
        )
        clauses.append(current)
        if "." in clause_id and section_clause is not None:
            section_clause.children.append(current)
        else:
            section_clause = current
        return current

    for page_no, text in enumerate(pages, start=1):
        if page_no == 1:
            cover = start("0", 0, "Capa: identificação e contato", 1)
            cover.lines = [ln for ln in (clean_line(x) for x in text.splitlines()) if ln]
            continue
        for raw in text.splitlines():
            line = clean_line(raw)
            if not line or HEADER_RE.match(line) or FOOTER_RE.match(line):
                continue

            m_sub = SUBSECTION_RE.match(line)
            if m_sub:
                major, minor = int(m_sub.group(1)), int(m_sub.group(2))
                if major == current_section and minor == last_sub + 1:
                    last_sub = minor
                    start(f"{major}.{minor}", major, m_sub.group(3), page_no)
                    continue

            m_sec = SECTION_RE.match(line)
            if m_sec and int(m_sec.group(1)) == expected_section:
                current_section = expected_section
                expected_section += 1
                last_sub = 0
                start(str(current_section), current_section, m_sec.group(2), page_no)
                continue

            if current is not None:
                current.lines.append(line)

    return clauses


def load_policy_clauses(pdf_path: Path) -> list[ClauseDraft]:
    return parse_clauses(extract_pages(pdf_path))


def find_policy_pdf(data_dir: Path) -> Path:
    matches = sorted(data_dir.glob("*.pdf"))
    if not matches:
        raise FileNotFoundError(f"nenhum PDF em {data_dir}")
    preferred = [p for p in matches if "pol" in p.name.lower()]
    return (preferred or matches)[0]
