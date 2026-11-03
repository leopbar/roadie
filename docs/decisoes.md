# Decisões de arquitetura

Registro curto das escolhas que moldam o projeto, com o que foi considerado e por que ficou assim.

## 1. Política como código e como texto, ao mesmo tempo

**Contexto.** O manual tem regras numéricas (7 dias, 30 dias, 5% de PIX, R$ 500 de frete grátis, faixas de parcela) e regras de conduta (tom de voz, privacidade, escopo).

**Decisão.** As regras numéricas viram funções puras em `backend/roadie/policy/rules.py`, cada uma devolvendo um veredito com a lista de cláusulas que o sustentam. O texto do manual é ingerido do PDF em cláusulas numeradas e fica disponível para busca. O modelo de linguagem chama a regra para prazos e contas e lê a cláusula para explicar.

**Por quê.** Modelos erram datas e aritmética de forma imprevisível; uma regra determinística erra sempre do mesmo jeito e tem teste. O teste de deriva (`test_rules.py::test_rule_parameters_still_match_the_manual_text`) confere que cada parâmetro do código ainda aparece literalmente na cláusula certa do PDF: se o manual mudar e o código não, o teste quebra.

**Alternativa descartada.** Deixar o modelo ler o manual e deduzir tudo. Funciona em demonstração e falha em produção, justamente nos casos de borda que importam (prazo que vence hoje, promoção que não acumula).

## 2. Recibo de evidências em cada resposta

**Decisão.** Cada mensagem do Tom carrega um recibo: ferramentas chamadas com argumentos e duração, tabelas e linhas lidas, cláusulas citadas, regras aplicadas, sinalizações de qualidade, tickets, modelo usado, uso de fallback, tokens, custo estimado e latência. O console mostra isso no painel *Bastidores* e as conversas de exemplo trazem o bloco por resposta.

**Por quê.** O avaliador precisa saber se o agente consultou ou inventou. A equipe da loja precisa auditar um atendimento. E o próprio desenvolvimento fica mais rápido: um recibo ruim aponta a ferramenta errada antes de ler a resposta.

## 3. Identidade por construção, não por prompt

**Decisão.** As ferramentas de pedido só enxergam os pedidos do cliente identificado na conversa. A identificação vem do telefone do remetente (como no WhatsApp) ou de número do pedido mais e-mail ou telefone, com três tentativas. O escopo é imposto no código das ferramentas (`backend/roadie/agent/tools.py`), não em instrução ao modelo.

**Por quê.** Os CSVs têm quase homônimos e um e-mail repetido; identificar por nome seria um vazamento esperando acontecer. Com o escopo no código, uma injeção de prompt que convença o modelo a "mostrar o pedido do Pedro" não tem efeito: a ferramenta devolve "não encontrado para este cliente".

## 4. Quarentena de dados, não limpeza

**Decisão.** A ingestão detecta contradições (marca do nome contra marca da descrição, specs contra texto, preço contra mediana da categoria, totais que não fecham, duplicidades) e grava etiquetas com severidade. Nada é apagado ou corrigido à mão.

**Por quê.** Corrigir à mão seria inventar dados. Apagar esconderia o problema da equipe. Marcar deixa o produto visível, faz o Tom tratar com cautela e dá à equipe uma lista do que consertar.

## 5. Relógio simulado

**Decisão.** O "agora" do agente vem de um relógio da loja configurável globalmente e por conversa, com padrão dois dias após o pedido mais recente dos dados.

**Por quê.** Prazos de política só fazem sentido relativos a uma data. Com o relógio real, nenhum cenário de devolução dos dados fornecidos seria demonstrável. Com o relógio simulado, as conversas de exemplo são reproduzíveis e o avaliador pode testar "fora do expediente" com um clique.

## 6. Busca textual no PostgreSQL em vez de banco vetorial

**Decisão.** As cláusulas do manual são indexadas com o full-text search do PostgreSQL em português, sem acentos, com peso maior no título, e seções-mãe são expandidas nas filhas. Não há embeddings nem vetores.

**Por quê.** O manual tem 29 cláusulas curtas e bem intituladas. Busca lexical com stemming em português acerta o alvo, custa zero por consulta, roda offline e cabe no mesmo banco. Embeddings seriam mais infraestrutura para o mesmo resultado. Se o acervo crescer para dezenas de documentos, `pgvector` entra no mesmo Postgres sem trocar de arquitetura.

## 7. LangGraph com um laço explícito de ferramentas

**Decisão.** Um grafo pequeno: nó do modelo, nó de ferramentas, roteamento condicional e limite de rodadas. Estado de conversa reconstruído do banco a cada mensagem.

**Por quê.** O laço de function calling precisa de limite, observabilidade e um ponto único para montar o prompt de sistema com relógio e identidade. O grafo deixa isso explícito e testável, sem a opacidade de um agente pré-pronto.

## 8. OpenAI com fallback automático, modelo simulado para testes

**Decisão.** Modelo principal e fallback configuráveis; se o principal falhar (cota, erro, indisponibilidade), o fallback responde e o recibo registra. Um modelo simulado determinístico roda o encanamento inteiro sem chave e sem custo, usado nos 67 testes.

**Por quê.** Indisponibilidade de provedor acontece. Testes que dependem de rede e de cobrança não rodam em CI nem na máquina do avaliador.

## 9. Chave do modelo cadastrável pelo console, cifrada no banco

**Decisão.** Além do `.env`, a chave pode ser cadastrada por um administrador na tela de Configurações, com teste de conexão em três passos. Fica cifrada com chave derivada de `SECRET_KEY`; o que está no banco prevalece sobre o ambiente.

**Por quê.** Trocar a chave em produção não deveria exigir acesso ao servidor nem reiniciar contêiner. A cifra garante que o banco sozinho não entrega o segredo.

## 10. Console em Next.js falando só com `/api`

**Decisão.** O navegador nunca conhece a URL da API: o Next reescreve `/api/*` para o serviço interno, e em produção o Caddy faz o mesmo. Sessão em cookies httpOnly com renovação e rotação.

**Por quê.** Mesma origem elimina CORS e deixa os cookies de sessão fora do alcance de JavaScript. O mesmo arranjo vale em desenvolvimento e na VPS.
