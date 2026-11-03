from roadie.ingest.policy_pdf import ClauseDraft, parse_clauses


def _by_id(clauses: list[ClauseDraft]) -> dict[str, ClauseDraft]:
    return {c.clause_id: c for c in clauses}


def test_manual_is_split_following_its_own_numbering(clauses: list[ClauseDraft]):
    ids = [c.clause_id for c in clauses]
    for expected in [
        "0",
        "1",
        "1.1",
        "1.2",
        "2",
        "3",
        "3.1",
        "4",
        "4.1",
        "4.2",
        "4.3",
        "4.4",
        "5",
        "5.1",
        "5.2",
        "5.3",
        "6",
        "6.1",
        "6.2",
        "7",
        "7.1",
        "7.2",
        "7.3",
        "8",
        "8.1",
        "8.2",
        "8.3",
        "9",
        "10",
    ]:
        assert expected in ids, expected
    # ordem preservada
    assert ids.index("4.1") < ids.index("4.2") < ids.index("5")


def test_numbered_lists_inside_sections_are_not_mistaken_for_sections(clauses: list[ClauseDraft]):
    titles = {c.title for c in clauses}
    assert not any(t.startswith("Saudação") for t in titles)
    flow = _by_id(clauses)["7.2"].body
    assert "Saudação" in flow and "Fechamento" in flow


def test_key_rules_are_present_in_the_right_clauses(clauses: list[ClauseDraft]):
    by = _by_id(clauses)
    assert "7 (sete) dias corridos" in by["4.1"].body
    assert "30 (trinta) dias corridos" in by["4.2"].body
    assert "09:00 às 18:00" in by["2"].body and "Fechado" in by["2"].body
    assert "5% de desconto" in by["3"].body
    assert "R$ 500,00" in by["5.1"].body and "R$ 35,00" in by["5.1"].body
    assert "90 (noventa) dias" in by["8.1"].body
    assert "não são cumulativas" in by["6.2"].body
    assert "BR4K7M2X9P1BR" in by["5.3"].body
    assert "Rua 14 de Maio, 3200" in by["1.2"].body
    assert "Sua música começa aqui" in by["0"].body


def test_bullets_are_merged_with_their_text(clauses: list[ClauseDraft]):
    body = _by_id(clauses)["4.4"].body
    assert "• Instrumentos com personalização" in body
    assert "\n•\n" not in body


def test_parser_ignores_running_headers_and_footers():
    pages = [
        "EMPÓRIO DA MÚSICA\nSua música começa aqui.\n",
        "Empório da Música Manual de Políticas e Procedimentos\n1. Primeira\ntexto a\n1.1 Sub\ntexto b\nPágina 2\n",
        "Empório da Música Manual de Políticas e Procedimentos\n2. Segunda\n1.​ Item de lista\n2. Outro item\nPágina 3\n",
    ]
    clauses = parse_clauses(pages)
    by = _by_id(clauses)
    assert set(by) == {"0", "1", "1.1", "2"}
    assert by["1"].body == "texto a"
    assert by["1.1"].body == "texto b"
    assert "Página" not in by["2"].body and "Manual de Políticas" not in by["2"].body
    assert "Item de lista" in by["2"].body and "Outro item" in by["2"].body
