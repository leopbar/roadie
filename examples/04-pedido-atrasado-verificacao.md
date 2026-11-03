# 4. Pedido atrasado com verificação de identidade

Número desconhecido pergunta por um pedido. O Tom não pode revelar nada antes de verificar a identidade com número do pedido e e-mail. Depois, descobre que o pedido está enviado e além da previsão de entrega, pede desculpas, informa o rastreio e abre um ticket de frete.

| | |
|---|---|
| Remetente | `(67) 98888-7777` |
| Relógio da loja | terça-feira, 24/03/2026 10:00 |
| Modelo | `gpt-6.1-terra` |
| Conversa | `b51e7398-c2f2-4392-88a2-d0667e7ef8ae` |
| Verificações | 7/7 |
| Custo estimado | US$ 0.0232 (21636 tokens) |
| Situação não trivial | sim: dados em tempo real e regras do manual |

## Conversa

**Cliente:** Oi, cadê meu pedido 8? Já devia ter chegado.

**Tom:** Oi! Poxa, entendo sua preocupação. Para eu consultar o pedido 8, me informe o e-mail ou telefone usado no cadastro, por favor.

<details>
<summary>Bastidores da resposta 1: 0 consulta(s), 2.1 s</summary>

> Sem identidade verificada, nenhuma informação do pedido pode sair.

- identidade: não identificado
- modelo: `gpt-6.1-terra` · 2905 tokens · US$ 0.0033

Verificações:

- ✅ resposta menciona “e-mail” | “email” | “telefone” | “confirmar” | “cadastro”
- ✅ resposta não menciona “BRJL5544332BR”

</details>

**Cliente:** O e-mail é anacarol.ferreira@coldmail.com

**Tom:** Ana, desculpa pelo atraso! Seu pedido 8 foi enviado, mas passou da previsão de entrega, que era 28/02/2026. O código de rastreio é BRJL5544332BR.  
  
Quer que eu registre uma solicitação para a equipe acompanhar a entrega?

<details>
<summary>Bastidores da resposta 2: 2 consulta(s), cláusulas 9, 5.1, 5.2, 5.3, 5.7 s</summary>

| # | Ferramenta | Argumentos | Resultado |
|---|---|---|---|
| 1 | `verificar_identidade` | `{"pedido_id": 8, "email": "anacarol.ferreira@coldmail.com"}` | ✅ identificado (pedido+email) (15.8 ms) |
| 2 | `consultar_pedido` | `{"pedido_id": 8}` | ✅ pedido 8: enviado (25.2 ms) |

- tabelas: `orders`, `customers`, `order_items`, `products`
- linhas: `orders#8`, `customers#2`
- cláusulas do manual: `§9`, `§5.1`, `§5.2`, `§5.3`
- regras determinísticas: `delivery_status`, `tracking_is_valid`
- identidade: Ana Carolina Ferreira (verificado por pedido+email)
- modelo: `gpt-6.1-terra` · 9080 tokens · US$ 0.0096

Verificações:

- ✅ chamou verificar_identidade
- ✅ resposta menciona “Ana” | “BRJL5544332BR” | “enviado” | “atras”

</details>

**Cliente:** Então abre um chamado pra vocês verificarem com a transportadora.

**Tom:** Ana, registrei o chamado para a equipe verificar o atraso com a transportadora. Desculpa pela demora!  
  
Protocolo: RD-2026-0005. A equipe retorna até 25/03/2026 às 10h.

<details>
<summary>Bastidores da resposta 3: 2 consulta(s), cláusulas 5.1, 5.2, 5.3, 7.3, 10, 5.7 s</summary>

| # | Ferramenta | Argumentos | Resultado |
|---|---|---|---|
| 1 | `consultar_pedido` | `{"pedido_id": 8}` | ✅ pedido 8: enviado (23.4 ms) |
| 2 | `abrir_ticket` | `{"categoria": "frete", "resumo": "Cliente solicita que a equipe verifique com a transportadora o atraso na entrega. Pedido enviado, com previsão de entrega em 28/02/2026; rastreio BRJL5544332BR.", "pedido_id": 8}` | ✅ ticket RD-2026-0005 (frete) (26.9 ms) |

- tabelas: `orders`, `order_items`, `products`, `tickets`
- linhas: `orders#8`, `tickets#RD-2026-0005`
- cláusulas do manual: `§5.1`, `§5.2`, `§5.3`, `§7.3`, `§10`
- regras determinísticas: `delivery_status`, `tracking_is_valid`, `complaint_sla`
- tickets: `RD-2026-0005` (frete)
- identidade: Ana Carolina Ferreira (verificado por pedido+email)
- modelo: `gpt-6.1-terra` · 9651 tokens · US$ 0.0104

Verificações:

- ✅ chamou abrir_ticket
- ✅ resposta menciona “RD-2026”
- ✅ abriu ticket

</details>
