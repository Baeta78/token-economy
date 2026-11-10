# Token Economy

Painel local e app de bandeja para acompanhar o consumo e a economia de tokens de todos os agentes desta máquina. Disponível em português, inglês e espanhol: escolha a língua no topo do painel, e o app da bandeja acompanha. Na primeira vez ele usa a língua do Windows.

[Read in English](README.md)

## Na bandeja (recomendado)

Precisa de Python 3.10+ e de `pip install pystray pillow`.

Dê dois cliques em `Token Economy.vbs`. Aparece um ícone na bandeja do Windows:

- **Mouse em cima:** limite do Codex (janela de 5 h e semanal), tokens novos de hoje, divisão entre agentes e economia do RTK.
- **Clique:** abre o painel numa janela própria.
- **Botão direito:** o mesmo resumo, "Atualizar agora", "Iniciar com o Windows" e "Sair".
- **Cor do ícone:** verde abaixo de 50% do limite do Codex, amarelo a partir de 50%, laranja a partir de 70%, vermelho a partir de 90%, cinza sem dados.

O Windows 11 esconde ícones novos na setinha `^`. Para deixar sempre visível, arraste o ícone para a barra, ou ative em Configurações > Personalização > Barra de tarefas > Outros ícones da bandeja do sistema.

Erros do app ficam em `.cache/tray.log`.

## Só no navegador

Dê dois cliques em `iniciar.bat`, ou rode no terminal:

```
python server.py
```

O painel abre em http://127.0.0.1:8765 e relê os dados a cada minuto. Feche a janela do terminal para parar.

Opções: `--porta 8765`, `--intervalo 60` (segundos entre leituras), `--sem-navegador`.

## O que ele lê

Tudo é lido localmente, só leitura, e nada sai da máquina.

| Ferramenta | Arquivo | O que dá para saber |
|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | tokens por chamada, modelo, projeto, ferramentas usadas |
| Limites do plano do Claude | Endpoint oficial de uso da Anthropic (`api.anthropic.com/api/oauth/usage`), com o login que o Claude Code guarda em `~/.claude/.credentials.json` | janelas de 5 h, semanal e semanal por modelo (as que o seu plano tiver) e o nome do plano. O token só vai para a Anthropic e não é gravado nem mostrado; dá para desligar em Ajustes |
| Codex | `~/.codex/sessions/**/rollout-*.jsonl` | tokens por turno, % da janela de 5 h e semanal, plano |
| OpenCode | `~/.local/share/opencode/opencode.db` | tokens e custo por resposta, inclusive modelos do Ollama |
| Ollama | `%LOCALAPPDATA%/Ollama/server*.log` | requisições e tempo de geração (o Ollama não grava tokens) |
| RTK | `%LOCALAPPDATA%/rtk/history.db` | tokens poupados por comando; o painel descobre de qual agente veio cada comando |
| Headroom | `~/.headroom/savings_events.jsonl` | tokens comprimidos pelo proxy, por cliente e modelo |
| Graphify | `<projeto>/graphify-out/graph.json` | onde há grafo e quantas vezes os agentes o usaram |

## Ferramentas de economia

O Token Economy detecta as ferramentas de economia de tokens instaladas na máquina e mostra **só essas**. Ele olha programas no PATH, hooks e servidores MCP registrados no Claude Code, Codex, OpenCode e Gemini CLI, skills e plugins instalados e a pasta de dados de cada ferramenta. Lê só nomes e comandos, nunca segredos.

As ferramentas que guardam a economia mostram tokens e US$ (mínimo e estimado com releituras do cache, a mesma conta para todas). As que não guardam dizem isso e mostram o que dá para saber: em que projetos cada uma está configurada (pelos arquivos dela no projeto ou por um MCP registrado só para o projeto) e quantas vezes os agentes a consultaram em cada projeto (chamadas pelo MCP ou pela skill e execuções do programa no terminal). O painel nunca inventa número.

São 19 ferramentas suportadas, todas conferidas no código-fonte de cada uma: RTK, Headroom, token-saver, squeez, Context Mode, lean-ctx, Token Optimizer, Caveman (no modo proxy), Kompact (com o proxy no ar), Code Context Engine e jCodeMunch registram a economia; Graphify, Serena, CodeGraph, codebase-memory-mcp, Claude Context, Token Reducer, claude-mem e TokenEconomizer não registram. A lista completa, com links e de onde cada número é lido, está no [README em inglês](README.md#token-saving-tools) e em `ferramentas_economia.json`.

## Abas

- **Resumo**: a visão de bater o olho. Nota de otimização, quanto vale o seu uso comparado com o que você paga, limites agora, uso por agente e ao longo do período, e os principais pontos (da análise por IA e das regras automáticas).
- **Consumo, Limites dos planos, Agentes e modelos, Economia, Projetos e sessões, Ferramentas**: o detalhe de cada número.
- **O que otimizar**: como a nota é calculada, a análise por IA e as regras automáticas.
- **Ajustes e fontes**: suas assinaturas, as tabelas de preço e de onde vem cada número.

## Nota de otimização

A nota (0 a 100) é calculada pelo código a partir de critérios que você consegue mudar: tamanho médio do contexto, parte das chamadas em sessões muito longas, aproveitamento do cache, parte dos tokens em modelos de ponta, quantos dos comandos que o RTK sabe comprimir passaram por ele, parte das chamadas de ferramenta que só esperam, e quantas janelas de 5 h do Codex chegaram a 95%. Cada critério tem um peso, uma meta que dá a pontuação cheia e um valor em que zera; no meio, é proporcional. Critérios sem dados ficam de fora e os pesos se redistribuem. "O que otimizar" mostra, para cada um, seu valor, a meta, os pontos e o que fazer. Pesos e metas ficam em `nota.py`.

## Assinaturas

Em Ajustes, cadastre cada assinatura com o valor mensal (US$) e o agente. O painel calcula a parte proporcional do período escolhido (7 dias de um plano de US$ 100/mês ≈ US$ 23) e compara com quanto o mesmo uso custaria pela API.

## Tokens ou dólares

O seletor **Tokens / US$** no topo mostra todos os gráficos em tokens ou no que o mesmo uso custaria pagando por token na API. Mesmo na assinatura, isso dá a medida do valor que você está usando e de quanto cada ferramenta poupa.

Os preços vêm de tabelas públicas que o painel baixa e atualiza toda semana: [LiteLLM](https://github.com/BerriAI/litellm) (milhares de modelos de todos os provedores) e, depois, o catálogo do [OpenRouter](https://openrouter.ai). Seus valores em `precos.json` têm prioridade; `precos_padrao.json` é a reserva sem internet. A aba Fontes mostra o preço e a fonte usados para cada modelo e tem o botão "Atualizar preços".

A economia do RTK em dólar aparece em dois números. O **mínimo** conta a saída poupada uma vez, pelo preço de entrada do modelo do agente. A **estimativa** (o valor mostrado por padrão) conta também as releituras do cache: sem o RTK, a saída ficaria na conversa e seria relida nas chamadas seguintes, até a compactação ou o fim da sessão tirá-la. Quanto tempo ela fica é estimado por sessão, pelo ritmo em que o contexto cresce.

## Análise por IA

Em "O que otimizar", escolha uma IA e clique em **Analisar com IA**. Ela lê um resumo dos seus números (nunca as conversas), compara com o período anterior e com a última análise, e devolve uma nota, um resumo e recomendações concretas. Abaixo, as regras automáticas continuam rodando a cada minuto, sem custo.

Jeitos de conectar a IA:

- **CLI instalada**, usando a assinatura que você já paga. O catálogo em `provedores_ia.json` cobre Claude Code, Codex, Gemini CLI, Qwen Code, Grok CLI, Cursor Agent, GitHub Copilot CLI, OpenCode, Factory Droid, Amp, Kimi e Ollama; o painel mostra as que estiverem no PATH. As marcadas com `"verificado": false` seguem a documentação de cada ferramenta, mas não foram testadas; dá para corrigir ou acrescentar ali.
- **Qualquer API compatível com OpenAI**: OpenAI, xAI (Grok), OpenRouter, Google Gemini, Groq, DeepSeek, Mistral, Ollama ou LM Studio. A chave fica só em `.cache/config.json` neste computador; também dá para escrever `$NOME_DA_VARIAVEL` para ler de uma variável de ambiente.
- **Comando personalizado**: qualquer programa que leia o prompt pela entrada padrão, ou pelo arquivo passado em `{arquivo}`, e devolva o JSON.

O prompt fica em `prompts/analise.md`; edite para mudar o que a IA observa. "Ver o que é enviado" mostra o texto exato. Cada análise gasta alguns milhares de tokens.

## Arquivos

- `tray.py`: o app da bandeja. Sobe o servidor e a coleta dentro dele.
- `server.py`: servidor local que coleta em segundo plano e entrega a página. Só a página do painel consegue mudar algo (os pedidos exigem um cabeçalho que outros sites não conseguem mandar).
- `sinais.py`, `economia.py`, `ferramentas_economia.json`: detecção das ferramentas de economia e leitura da economia delas.
- `collector.py`: lê as fontes e monta os números. Pode ser rodado sozinho para testar: `python collector.py`.
- `precos.py`, `precos.json`, `precos_padrao.json`: preços (veja acima).
- `ia.py`, `provedores_ia.json`, `prompts/analise.md`: a análise por IA.
- `static/`: a página (HTML, CSS, JS). As traduções ficam em `static/i18n.js`. Os gráficos usam Chart.js do cdnjs, então precisam de internet.
- `.cache/`: até onde cada arquivo já foi lido, tabelas de preço baixadas, configurações, análises anteriores e o log da bandeja. Pode apagar; a próxima leitura refaz tudo.

## Limitações

- O Claude Code não grava o % dos limites do plano. O painel mostra quando o Headroom tem uma leitura recente; senão, use `/usage` no Claude Code.
- Tokens do RTK são estimados (bytes ÷ 4). Saídas acima de 7.500 tokens ficam fora da conta, igual ao `rtk gain`.
- O agente de cada comando do RTK é deduzido comparando com os comandos que cada agente executou; cerca de 5% fica como "não identificado".
