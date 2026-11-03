# Premissas, ambiguidades e o que os dados escondem

O enunciado pede que ambiguidades sejam resolvidas com uma interpretação razoável e documentadas. Este é o registro.

## Sobre o manual de políticas

| Ambiguidade | Interpretação adotada |
|---|---|
| Dois números de WhatsApp: (67) 3341-4444 na ficha da empresa (1.2) e (67) 3321-4500 no canal de atendimento (7) | O Tom informa os dois com a distinção que o manual faz: telefone/WhatsApp da loja e canal de atendimento. |
| E-mail com acento em um trecho (`contato@empóriodamusica.com.br`) e sem acento na capa | O Tom usa o endereço sem acento, que é o único tecnicamente válido. |
| Tabela da seção 3 diz "parcela mínima de R$ 100,00" para crédito; a seção 3.1 detalha faixas (R$ 50 até 3x, R$ 80 de 4x a 6x, R$ 100 de 7x a 12x) | A seção 3.1 prevalece por ser mais específica. O veredito de parcelamento registra a divergência. |
| "Frete grátis para pedidos acima de R$ 500,00" e "abaixo de R$ 500,00, taxa fixa": R$ 500,00 exatos não está em nenhuma das duas | Frete grátis a partir de R$ 500,00 (interpretação favorável ao cliente). |
| "24 horas úteis" para retorno de reclamação | Um dia útil a partir do próximo momento de expediente: terça 10h vira quarta 10h; sábado vira terça 9h. |
| Região metropolitana de Campo Grande sem lista de municípios | Campo Grande e vizinhos imediatos (Terenos, Jaraguari, Sidrolândia, Ribas do Rio Pardo, Nova Alvorada do Sul, Rochedo, Corguinho). Dourados, Três Lagoas, Corumbá e Ponta Porã caem na regra de Correios/Jadlog com cotação. |
| Direito de arrependimento vale só para compras online | Todos os pedidos dos CSVs têm envio e rastreio, então são tratados como compras online. |
| "Após o recebimento do produto" como início do prazo, mas o sistema não registra a data de recebimento | Para pedidos entregues, a data estimada de entrega é o melhor substituto, e o veredito diz isso. Se o cliente informar a data real, ela prevalece. Para pedidos enviados sem data, o Tom pergunta. |
| Cancelamento antes do envio não está no manual | Pedidos pendentes ou confirmados viram pedido de cancelamento registrado para a equipe, seguindo a prática visível nos próprios dados (pedido 17: "cancelado pelo cliente antes do processamento"). |
| Feriados não aparecem no manual nem nos dados | Dias úteis são segunda a sexta. Feriados ficam como limitação conhecida. |
| "Sugerir lojas parceiras" para acessórios, sem lista de parceiras | O Tom diz que a equipe pode indicar, sem inventar nomes. |
| "Mais de 300 instrumentos" no manual contra 65 nos CSVs | Os CSVs são a verdade operacional. O Tom nunca cita o tamanho do catálogo. |

## Sobre os dados

A ingestão marca cada problema em vez de corrigir ou apagar. O comando `roadie quality` lista tudo; a tela *Qualidade de dados* do console mostra o mesmo.

### Em quarentena (o Tom não afirma preço nem especificação)

| Produto | O que há de errado |
|---|---|
| 135 Music Man Bass 1X | Nome diz Music Man; descrição descreve um Fender Jazz Bass. |
| 136 Ibanez Bass 2X | R$ 441,00, cerca de 5% da mediana dos baixos; descontinuado com 13 unidades em estoque. |
| 137 Yamaha Bass 3X | Nome diz Yamaha; descrição descreve um Ibanez de 5 cordas; specs dizem 4 cordas. |
| 139 Bateria Yamaha Kit 1 | Descrição é de uma Pearl Export. |
| 140 Bateria Pearl Kit 2 | Descrição é de uma Tama. |
| 142 Teclado Korg Synth 1 Pro | Descrição é de um Roland de 88 teclas; specs dizem 61; preço de R$ 1.127 para uma workstation. |
| 144 Teclado Roland Synth 3 Pro | Descrição é de um arranjador Yamaha. |

Os dez produtos com nomes genéricos ("Bass 1X", "Kit 2", "Synth 3") recebem um alerta de nome genérico; os que não têm contradição (138, 141, 143) continuam vendáveis normalmente.

### Alertas (o Tom responde com ressalva)

- Pedidos 3 e 20 têm total diferente da soma dos itens (R$ 3.450 contra R$ 3.498; R$ 1.400 contra R$ 1.488). O total do pedido é tratado como o valor pago.
- Clientes 11 e 43 compartilham o mesmo e-mail (`bruno.martins@jmail.com`).

### Só registro

- Produto 96 (Giannini GF-3D) está ativo com estoque zero: o Tom diz "temporariamente indisponível" e sugere alternativas.
- Produto 130 (ukulele barítono Kala) está "em breve" e aparece no pedido 14, pendente: tratado como pré-venda.
- As categorias de sopros (madeiras e metais) e de cordas orquestrais existem mas não têm nenhum produto: o Tom diz isso em vez de inventar modelos.
- Quase homônimos no cadastro ("Bruno Carvalho Martins", "Bruno Carvalho", "Bruno Martins"; "Diego Fernandes Castro" e "Diego Castro"): é por isso que a identidade nunca é inferida pelo nome.

## Sobre o tempo

Os pedidos vão de outubro de 2025 a março de 2026. Com o relógio real, todo prazo de arrependimento já teria vencido e o cenário de devolução sugerido no enunciado seria impossível de demonstrar. Por isso o "agora" do agente é simulado e configurável (`STORE_CLOCK` no `.env`, e por conversa no console), com padrão em terça-feira, 24/03/2026 às 10:00, dois dias depois do pedido mais recente. `STORE_CLOCK=real` usa o relógio do servidor.

## Sobre os modelos

Os nomes padrão (`gpt-6.1-terra` como principal, `gpt-6-luna` como fallback) e a tabela de preços para estimar custo vêm da página oficial de preços da OpenAI em 03/11/2026. São configuráveis no `.env` e pelo console, sem mexer em código.
