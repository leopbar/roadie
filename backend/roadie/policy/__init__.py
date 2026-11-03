"""Políticas da loja como código.

O manual em PDF vira dois artefatos complementares:
- cláusulas de texto (ingest/policy_pdf.py), que o agente lê e cita;
- regras determinísticas (policy/rules.py), que fazem as contas e as datas
  e devolvem um veredito com o número da cláusula que o justifica.

O modelo de linguagem nunca calcula prazo, parcela ou desconto: ele chama
a regra e explica o resultado.
"""
