"use strict";
// Token Economy translations. To add a language, copy the "en" block and translate it.
// {name} is replaced by the value passed in t("key", { name: value }).

const LANGUAGES = { pt: "Português", en: "English", es: "Español" };
const LOCALES = { pt: "pt-BR", en: "en-US", es: "es-ES" };

const TXT = {
  // ---------------------------------------------------------------- Portuguese
  pt: {
    app: "Token Economy",
    "period.label": "Período",
    "period.today": "Hoje", "period.24h": "24 h", "period.7d": "7 dias", "period.30d": "30 dias", "period.all": "Tudo",
    "period.name.today": "hoje", "period.name.24h": "nas últimas 24 h", "period.name.7d": "nos últimos 7 dias", "period.name.30d": "nos últimos 30 dias", "period.name.all": "em todo o histórico",
    "btn.refresh": "Atualizar", "btn.refresh.hint": "Ler os dados de novo agora", "btn.reading": "Lendo…", "btn.theme": "Alternar tema claro/escuro", "language": "Idioma",
    "tab.overview": "Visão geral", "tab.limits": "Limites dos planos", "tab.models": "Agentes e modelos", "tab.savings": "Economia", "tab.projects": "Projetos e sessões", "tab.tools": "Ferramentas", "tab.tips": "O que otimizar", "tab.sources": "Fontes",
    "loading.title": "Lendo os registros dos agentes…", "loading.sub": "Na primeira vez lê todo o histórico. Depois só o que mudou.", "loading.offline": "Servidor fora do ar. Abra o Token Economy de novo.", "loading.error": "Erro: {msg}",
    "header.data": "dados de {when} · atualiza a cada minuto", "header.loading": "carregando…",
    "agent.claude": "Claude Code", "agent.codex": "Codex", "agent.opencode": "OpenCode", "agent.ollama": "Ollama", "agent.unknown": "Não identificado",
    "proj.~none": "(sem pasta)", "proj.~temp": "(pasta temporária)",
    "empty": "Sem dados no período.", "no.charts": "Gráficos indisponíveis: sem acesso ao cdnjs.cloudflare.com.", "sort": "Ordenar",
    "now": "agora", "days": "{n} dias",

    "overview.daily": "Tokens novos por dia", "overview.daily.explain": "Entrada sem cache + escrita em cache + saída. É o que mais pesa no limite. Leitura de cache fica fora porque custa ~10% do preço.", "overview.byHour": "por hora", "overview.byDay": "por dia",
    "overview.consumes": "Quem consome mais", "overview.consumes.explain": "Parte de cada agente nos tokens novos do período.",
    "overview.saves": "Quem economiza mais", "overview.saves.explain": "Tokens que deixaram de entrar no contexto graças ao RTK e ao Headroom.",
    "kpi.new": "Tokens novos", "kpi.new.det": "{n} chamadas ao modelo {period}", "kpi.new.hint": "Entrada sem cache + escrita em cache + saída",
    "kpi.cache": "Lidos do cache", "kpi.cache.det": "{pct} da entrada veio do cache", "kpi.cache.hint": "Leitura de cache custa cerca de 10% do preço normal",
    "kpi.api": "Equivalente em API", "kpi.api.unpriced": "{n} tokens sem preço", "kpi.api.table": "pelo preço de tabela", "kpi.api.hint": "Quanto custaria pagando por token. Na assinatura o que limita é a janela de 5 h e a semanal.",
    "kpi.rtk": "Economia do RTK", "kpi.rtk.det": "{pct} da saída de {n} comandos", "kpi.rtk.hint": "Tokens de saída de comandos que não entraram no contexto",
    "kpi.hr": "Economia do Headroom", "kpi.hr.det": "{n} requisições pelo proxy", "kpi.hr.hint": "Tokens comprimidos pelo proxy do Headroom",
    "calls": "{n} chamadas",

    "lim.codex5h": "Codex: janela de 5 horas", "lim.codexWeek": "Codex: limite semanal", "lim.plan": "plano {p}",
    "lim.chart": "Uso da janela de 5 h do Codex ao longo do tempo", "lim.chart.explain": "Cada degrau que volta a zero é uma janela nova. Inclinação forte = limite gasto rápido.",
    "lim.windows": "Janelas de 5 h recentes do Codex", "lim.claude": "Claude: limites", "lim.last5h": "Tokens nas últimas 5 horas", "lim.last5h.explain": "Comparação direta do volume recente de cada agente.",
    "lim.noCodex": "O Codex ainda não registrou limites.",
    "lim.resets": "Reinicia", "lim.free": "janela livre, nenhuma em curso", "lim.rate": "Ritmo desta janela", "lim.perHour": "{pct} por hora", "lim.perDay": "{pct} por dia",
    "lim.fullIn": "Nesse ritmo, 100% em", "lim.avgRate": "Ritmo médio (últimas 10 janelas)", "lim.lastReading": "Última leitura",
    "lim.weekRate": "Ritmo da semana", "lim.weekEnd": "Nesse ritmo, fim da semana em", "lim.weekReadings": "Leituras nesta semana",
    "lim.series5h": "Janela de 5 h", "lim.seriesWeek": "Semanal",
    "st.reached": "Limite atingido", "st.willRunOut": "Vai estourar antes do reset", "st.attention": "Atenção", "st.calm": "Tranquilo",
    "col.windowStart": "Início da janela", "col.used": "Usado", "col.rate": "Ritmo (%/h)", "col.wouldRunOut": "Esgotaria em", "col.wouldRunOut.hint": "Tempo para chegar a 100% mantendo o ritmo da janela", "col.lastReading": "Última leitura",
    "lim.claude.5h": "Janela de 5 h reinicia", "lim.claude.no": "Semanal", "lim.claude.source": "Fonte", "lim.claude.headroom": "Headroom, {when}",
    "lim.claude.noData": "O Claude Code não grava o percentual dos limites nos registros dele. O Headroom consegue ler quando o proxy dele está ligado", "lim.claude.stale": ", mas a última leitura é de {date} ({when}), velha demais para valer",
    "lim.claude.usage": "Para ver o número exato agora: digite <b>/usage</b> no Claude Code. Abaixo, o volume recente de tokens serve de termômetro.",
    "lim.peak": "{pct} do seu pico de 5 h", "lim.peak.hint": "{n} chamadas · pico de 5 h nos últimos 30 dias: {peak}", "lim.peak.explain": "\"Pico\" é a janela de 5 h com mais tokens novos nos últimos 30 dias.",

    "mod.table": "Consumo por agente e modelo", "mod.table.explain": "\"Entrada/chamada\" mostra o peso médio de cada chamada: contexto grande repetido é o principal gasto. \"Cache\" é a parte da entrada servida do cache (quanto maior, mais barato).",
    "mod.perHour": "Tokens novos ao longo do tempo", "mod.composition": "Composição da entrada", "mod.composition.explain": "Como cada agente monta o contexto que manda ao modelo.",
    "mod.hourOfDay": "Horário de uso", "mod.hourOfDay.explain": "Tokens novos por hora do dia, somando o período.",
    "col.agent": "Agente", "col.model": "Modelo", "col.calls": "Chamadas", "col.new": "Tokens novos", "col.inputPerCall": "Entrada/chamada", "col.inputPerCall.hint": "Tamanho médio do contexto enviado em cada chamada",
    "col.cache": "Cache", "col.cache.hint": "Parte da entrada lida do cache", "col.outputPerCall": "Saída/chamada", "col.reasoning": "Raciocínio", "col.reasoning.hint": "Tokens de raciocínio informados (só o Codex e o OpenCode registram)", "col.api": "Equivalente API", "unpriced": "sem preço",
    "comp.cr": "Leitura de cache", "comp.cw": "Escrita em cache", "comp.input": "Entrada sem cache", "comp.out": "Saída",

    "sav.perDay": "Economia por dia", "sav.rtkCmd": "RTK por comando", "sav.rtkCmd.explain": "Comandos que mais passaram pelo RTK. \"Sem ganho\" conta as vezes em que o filtro não reduziu nada.",
    "sav.hook": "Cobertura do hook do RTK", "sav.hook.explain": "Decisões do hook no Claude Code. Só comandos de shell passam por ele.",
    "sav.failures": "Falhas do RTK", "sav.failures.explain": "Comandos que o RTK não conseguiu filtrar e rodou sem compressão.", "sav.failures.total": "{n} falhas no histórico todo. Quando falha, o comando roda normal, só sem compressão.",
    "sav.headroom": "Headroom por cliente e modelo",
    "kpi.rtkSaved": "RTK: tokens poupados", "kpi.rtkSaved.det": "{pct} da saída de comandos", "kpi.rtkCmds": "RTK: comandos filtrados", "kpi.rtkCmds.det": "{n} saídas gigantes fora da conta", "kpi.rtkCmds.hint": "O RTK ignora na conta saídas acima de 7.500 tokens, que o agente cortaria de qualquer jeito",
    "kpi.hrSaved": "Headroom: tokens poupados", "kpi.hrSaved.det": "{pct} do que passou pelo proxy", "kpi.hrSaved.reqs": "{n} requisições",
    "kpi.savTotal": "Economia sobre o consumo", "kpi.savTotal.det": "suas ferramentas em relação aos tokens novos", "kpi.savTotal.hint": "Quanto os tokens novos teriam sido maiores sem as suas ferramentas de economia. Conta aproximada: o RTK estima tokens como bytes ÷ 4.",
    "col.command": "Comando", "col.runs": "Vezes", "col.saved": "Tokens poupados", "col.reduction": "Redução", "col.reduction.hint": "Só eventos que registram o tamanho original", "col.noGain": "Sem ganho",
    "dec.defer": "Reescrito para o RTK", "dec.ask": "Reescrito, pedindo permissão", "dec.allow": "Liberado sem reescrever", "dec.deny": "Bloqueado",
    "sav.attrib": "Agente de cada comando do RTK: {a} identificado pelo texto do comando, {b} pelo agente ativo no momento, {c} sem identificação.",
    "col.client": "Cliente", "col.reqs": "Requisições", "col.usdSaved": "US$ poupados",

    "proj.top": "Projetos que mais consomem", "proj.sessions": "Sessões mais pesadas",
    "col.project": "Projeto", "col.agents": "Agentes", "col.tokensCache": "Tokens (com cache)", "col.share": "Parte", "col.start": "Início", "col.duration": "Duração", "col.avgCtx": "Contexto médio", "col.avgCtx.hint": "Tokens de entrada por chamada. Contexto grande repetido é o que mais gasta.", "col.tokens": "Tokens",

    "tools.title": "{agent}: ferramentas", "tools.explain": "Chamadas de ferramenta em todo o histórico.", "tools.shell": "Comandos de shell mais usados", "tools.shell.explain": "Primeira palavra de cada comando.",
    "gf.explain": "O Graphify não registra tokens economizados. O painel mostra onde existe grafo pronto e quantas vezes os agentes recorreram a ele.",
    "gf.projects": "Projetos com grafo", "gf.calls": "Chamadas registradas", "gf.none": "nenhuma", "col.folder": "Pasta", "col.size": "Tamanho", "col.updated": "Atualizado",
    "ol.title": "Ollama (modelos locais)", "ol.explain": "O Ollama não grava tokens nos logs, só as requisições e quanto tempo cada uma levou. Tokens aparecem quando ele é usado pelo OpenCode.",
    "ol.reqs": "Requisições", "ol.time": "Tempo de geração", "ol.errors": "{n} com erro", "ol.viaOC": "Tokens via OpenCode", "ol.installed": "Modelos instalados", "ol.loaded": "carregado agora: {m}", "ol.none": "nenhum carregado agora",

    "tips.title": "O que dá para otimizar", "tips.explain": "Calculado a partir dos seus dados do período selecionado.", "tips.nothing": "Nada a sugerir com os dados do período.",
    "level.high": "Prioridade alta", "level.medium": "Prioridade média", "level.low": "Sugestão", "level.ok": "Informação",
    "d.codexRtk.t": "O Codex quase não passa pelo RTK",
    "d.codexRtk.p": "{Period} o Codex fez {n} chamadas e só {r} comandos dele foram filtrados pelo RTK. {pct} dos comandos de shell do Codex são PowerShell (Get-Content, Get-ChildItem…), que o RTK não comprime. Cada arquivo lido assim entra inteiro no contexto.",
    "d.codexRtk.a": "Peça ao Codex, no AGENTS.md, para usar rg, cat e ls pelo Git Bash (ou rtk read / rtk grep) em vez de Get-Content e Select-String.",
    "d.rate.t": "O Codex gasta em média {pct} da janela de 5 h por hora",
    "d.rate.p": "Nesse ritmo a janela de 5 h acaba em {dur}{overrun}. O plano {plan} é o fator limitante: o Codex lê contexto grande a cada turno{ctx}.",
    "d.rate.overrun": "; {n} das últimas {m} janelas chegaram a 100%", "d.rate.ctx": " (média de {n} tokens de entrada por chamada)",
    "d.rate.a": "Use o Codex para tarefas curtas e bem delimitadas e deixe as sessões longas para o Claude Code. Para reduzir por turno: modelo menor em tarefas simples e sessões novas com mais frequência.",
    "d.cache.t": "O Codex reaproveita menos cache que o Claude Code",
    "d.cache.p": "{a} da entrada do Codex vem do cache, contra {b} no Claude Code. Entrada sem cache conta inteira no limite.",
    "d.cache.a": "Evite trocar de modelo ou de nível de raciocínio no meio da sessão e evite editar o AGENTS.md durante o trabalho: as duas coisas invalidam o cache.",
    "d.opus.t": "{pct} do Claude Code roda no Opus",
    "d.opus.p": "O Sonnet 5.5 custa metade por token (US$ 2/10 contra US$ 4/20 do Opus 5.5). Pelo preço de API, o Opus somou {usd} {period}.",
    "d.opus.a": "Use Sonnet para subagentes de busca e leitura (Explore) e tarefas mecânicas; mantenha Opus para planejar e para código difícil.",
    "d.ctx.t": "Contexto médio do Claude Code: {n} tokens por chamada",
    "d.ctx.p": "Cada chamada reenvia o histórico inteiro da conversa. Mesmo com cache, sessões muito longas pesam no limite.",
    "d.ctx.a": "Comece sessões novas ao trocar de assunto e use /compact quando a conversa passar de ~200 mil tokens.",
    "d.sess.t1": "1 sessão passou de 50 milhões de tokens", "d.sess.tn": "{n} sessões passaram de 50 milhões de tokens",
    "d.sess.p": "A maior: {proj} ({agent}), {tok} tokens em {n} chamadas.",
    "d.sess.a": "Veja a aba Projetos e sessões. Sessões assim costumam ser laços de espera ou tarefas que poderiam ser divididas.",
    "d.waits.t": "{n} chamadas de ferramentas de espera no Claude Code",
    "d.waits.p": "Cada chamada de espera ({list}) reenvia o contexto inteiro ao modelo só para checar se algo terminou.",
    "d.waits.a": "Prefira esperas longas (timeout maior) ou rodar o processo em segundo plano e ser avisado no fim, em vez de consultar o status em laço.",
    "d.failure.t": "O RTK falha em \"{cmd}\" ({n} vezes)",
    "d.failure.p": "O comando ainda roda, mas sem compressão e com o custo de tentar filtrar antes.",
    "d.failure.a": "Adicione \"{cmd}\" em exclude_commands na seção [hooks] do config.toml do RTK, ou reporte o caso ao projeto do RTK.",
    "d.noGain.t": "Comandos que o RTK reescreve sem reduzir nada",
    "d.noGain.item": "{cmd} ({pct} sem ganho em {n} execuções)",
    "d.noGain.a": "Normal para saídas que já são curtas. Se algum desses tiver saída longa, compare com rtk bypass para ver o filtro.",
    "d.hr.t1": "O Headroom comprimiu só {pct} do que passou por ele", "d.hr.t0": "O proxy do Headroom não teve tráfego no período",
    "d.hr.p1": "A última requisição pelo proxy foi {when}. Fora isso, os agentes falam direto com a API e o Headroom não atua.", "d.hr.p0": "Nenhuma requisição registrada pelo proxy.",
    "d.hr.a": "Rode headroom doctor para ver se o proxy está no ar e se os agentes apontam para ele. Se não compensar, desligue para não somar latência.",
    "d.gf.t": "O Graphify quase não está sendo usado",
    "d.gf.p": "Só {n} projeto(s) têm grafo gerado e os agentes chamaram o Graphify {c} vez(es). Sem grafo, o agente lê arquivos inteiros para entender o código.",
    "d.gf.a": "Gere o grafo nos projetos grandes que você mais usa (veja a aba Projetos e sessões) e lembre o agente de consultá-lo antes de abrir arquivos.",
    "d.share.t": "{agent} responde por {pct} dos tokens novos", "d.share.p": "Distribuição {period}: {list}.",

    "sources.title": "De onde vêm os dados", "col.tool": "Ferramenta", "col.file": "Arquivo", "col.status": "Status", "col.read": "Lido",
    "sources.ok": "ok", "sources.no": "não encontrado",
    "sources.claude": "{n} arquivos de sessão", "sources.codex": "{n} sessões, {m} leituras de limite", "sources.opencode": "{n} respostas do modelo", "sources.ollama": "{n} requisições de geração", "sources.rtk": "{n} comandos", "sources.headroom": "{n} eventos de economia", "sources.graphify": "{n} projetos com grafo",
    "sources.note": "Coleta feita em {s} s. Tudo é lido localmente e nada sai da máquina. Os preços do \"equivalente em API\" ficam em <code>prices.json</code>; modelos sem preço podem ser preenchidos lá.",
  },

  // ---------------------------------------------------------------- English
  en: {
    app: "Token Economy",
    "period.label": "Period",
    "period.today": "Today", "period.24h": "24 h", "period.7d": "7 days", "period.30d": "30 days", "period.all": "All",
    "period.name.today": "today", "period.name.24h": "in the last 24 h", "period.name.7d": "in the last 7 days", "period.name.30d": "in the last 30 days", "period.name.all": "across all history",
    "btn.refresh": "Refresh", "btn.refresh.hint": "Read the data again now", "btn.reading": "Reading…", "btn.theme": "Toggle light/dark theme", "language": "Language",
    "tab.overview": "Overview", "tab.limits": "Plan limits", "tab.models": "Agents & models", "tab.savings": "Savings", "tab.projects": "Projects & sessions", "tab.tools": "Tools", "tab.tips": "What to optimize", "tab.sources": "Sources",
    "loading.title": "Reading the agents' logs…", "loading.sub": "The first run reads the whole history. After that, only what changed.", "loading.offline": "Server is down. Open Token Economy again.", "loading.error": "Error: {msg}",
    "header.data": "data from {when} · refreshes every minute", "header.loading": "loading…",
    "agent.claude": "Claude Code", "agent.codex": "Codex", "agent.opencode": "OpenCode", "agent.ollama": "Ollama", "agent.unknown": "Unidentified",
    "proj.~none": "(no folder)", "proj.~temp": "(temporary folder)",
    "empty": "No data in this period.", "no.charts": "Charts unavailable: no access to cdnjs.cloudflare.com.", "sort": "Sort",
    "now": "now", "days": "{n} days",

    "overview.daily": "New tokens per day", "overview.daily.explain": "Uncached input + cache writes + output. This is what weighs most on your limit. Cache reads are left out because they cost ~10% of the price.", "overview.byHour": "per hour", "overview.byDay": "per day",
    "overview.consumes": "Who uses the most", "overview.consumes.explain": "Each agent's share of new tokens in the period.",
    "overview.saves": "Who saves the most", "overview.saves.explain": "Tokens kept out of the context by RTK and Headroom.",
    "kpi.new": "New tokens", "kpi.new.det": "{n} model calls {period}", "kpi.new.hint": "Uncached input + cache writes + output",
    "kpi.cache": "Read from cache", "kpi.cache.det": "{pct} of input came from cache", "kpi.cache.hint": "Cache reads cost about 10% of the normal price",
    "kpi.api": "API equivalent", "kpi.api.unpriced": "{n} tokens without a price", "kpi.api.table": "at list price", "kpi.api.hint": "What this would cost paying per token. On a subscription, the 5-hour and weekly windows are what limit you.",
    "kpi.rtk": "RTK savings", "kpi.rtk.det": "{pct} of the output of {n} commands", "kpi.rtk.hint": "Command output tokens that never reached the context",
    "kpi.hr": "Headroom savings", "kpi.hr.det": "{n} requests through the proxy", "kpi.hr.hint": "Tokens compressed by the Headroom proxy",
    "calls": "{n} calls",

    "lim.codex5h": "Codex: 5-hour window", "lim.codexWeek": "Codex: weekly limit", "lim.plan": "{p} plan",
    "lim.chart": "Codex 5-hour window usage over time", "lim.chart.explain": "Each drop back to zero is a new window. A steep slope means the limit is going fast.",
    "lim.windows": "Recent Codex 5-hour windows", "lim.claude": "Claude: limits", "lim.last5h": "Tokens in the last 5 hours", "lim.last5h.explain": "Side-by-side look at each agent's recent volume.",
    "lim.noCodex": "Codex hasn't recorded any limits yet.",
    "lim.resets": "Resets", "lim.free": "no window in progress", "lim.rate": "Pace of this window", "lim.perHour": "{pct} per hour", "lim.perDay": "{pct} per day",
    "lim.fullIn": "At this pace, 100% in", "lim.avgRate": "Average pace (last 10 windows)", "lim.lastReading": "Last reading",
    "lim.weekRate": "Weekly pace", "lim.weekEnd": "At this pace, end of week at", "lim.weekReadings": "Readings this week",
    "lim.series5h": "5-hour window", "lim.seriesWeek": "Weekly",
    "st.reached": "Limit reached", "st.willRunOut": "Will run out before reset", "st.attention": "Watch out", "st.calm": "All good",
    "col.windowStart": "Window start", "col.used": "Used", "col.rate": "Pace (%/h)", "col.wouldRunOut": "Would run out in", "col.wouldRunOut.hint": "Time to reach 100% keeping the window's pace", "col.lastReading": "Last reading",
    "lim.claude.5h": "5-hour window resets", "lim.claude.no": "Weekly", "lim.claude.source": "Source", "lim.claude.headroom": "Headroom, {when}",
    "lim.claude.noData": "Claude Code doesn't write its limit percentages to its logs. Headroom can read them while its proxy is running", "lim.claude.stale": ", but the last reading is from {date} ({when}), too old to rely on",
    "lim.claude.usage": "To see the exact number now, type <b>/usage</b> in Claude Code. Below, recent token volume works as a gauge.",
    "lim.peak": "{pct} of your 5-hour peak", "lim.peak.hint": "{n} calls · 5-hour peak in the last 30 days: {peak}", "lim.peak.explain": "\"Peak\" is the 5-hour window with the most new tokens in the last 30 days.",

    "mod.table": "Usage by agent and model", "mod.table.explain": "\"Input/call\" shows the average weight of each call: a large context sent over and over is the main cost. \"Cache\" is the share of input served from cache (higher is cheaper).",
    "mod.perHour": "New tokens over time", "mod.composition": "Input breakdown", "mod.composition.explain": "How each agent builds the context it sends to the model.",
    "mod.hourOfDay": "Time of day", "mod.hourOfDay.explain": "New tokens by hour of day, summed over the period.",
    "col.agent": "Agent", "col.model": "Model", "col.calls": "Calls", "col.new": "New tokens", "col.inputPerCall": "Input/call", "col.inputPerCall.hint": "Average size of the context sent in each call",
    "col.cache": "Cache", "col.cache.hint": "Share of input read from cache", "col.outputPerCall": "Output/call", "col.reasoning": "Reasoning", "col.reasoning.hint": "Reported reasoning tokens (only Codex and OpenCode record them)", "col.api": "API equivalent", "unpriced": "no price",
    "comp.cr": "Cache read", "comp.cw": "Cache write", "comp.input": "Uncached input", "comp.out": "Output",

    "sav.perDay": "Savings per day", "sav.rtkCmd": "RTK by command", "sav.rtkCmd.explain": "Commands that went through RTK the most. \"No gain\" counts the times the filter didn't reduce anything.",
    "sav.hook": "RTK hook coverage", "sav.hook.explain": "Hook decisions in Claude Code. Only shell commands go through it.",
    "sav.failures": "RTK failures", "sav.failures.explain": "Commands RTK couldn't filter and ran uncompressed.", "sav.failures.total": "{n} failures across all history. When it fails, the command still runs, just uncompressed.",
    "sav.headroom": "Headroom by client and model",
    "kpi.rtkSaved": "RTK: tokens saved", "kpi.rtkSaved.det": "{pct} of command output", "kpi.rtkCmds": "RTK: commands filtered", "kpi.rtkCmds.det": "{n} huge outputs left out", "kpi.rtkCmds.hint": "RTK leaves out outputs above 7,500 tokens, which the agent would truncate anyway",
    "kpi.hrSaved": "Headroom: tokens saved", "kpi.hrSaved.det": "{pct} of what went through the proxy", "kpi.hrSaved.reqs": "{n} requests",
    "kpi.savTotal": "Savings vs. usage", "kpi.savTotal.det": "your tools relative to new tokens", "kpi.savTotal.hint": "How much larger new tokens would have been without your token-saving tools. Approximate: RTK estimates tokens as bytes ÷ 4.",
    "col.command": "Command", "col.runs": "Runs", "col.saved": "Tokens saved", "col.reduction": "Reduction", "col.reduction.hint": "Only events that record the original size", "col.noGain": "No gain",
    "dec.defer": "Rewritten to RTK", "dec.ask": "Rewritten, asking permission", "dec.allow": "Allowed without rewrite", "dec.deny": "Blocked",
    "sav.attrib": "Agent for each RTK command: {a} matched by command text, {b} by the agent active at the time, {c} unidentified.",
    "col.client": "Client", "col.reqs": "Requests", "col.usdSaved": "US$ saved",

    "proj.top": "Projects that use the most", "proj.sessions": "Heaviest sessions",
    "col.project": "Project", "col.agents": "Agents", "col.tokensCache": "Tokens (incl. cache)", "col.share": "Share", "col.start": "Start", "col.duration": "Duration", "col.avgCtx": "Avg. context", "col.avgCtx.hint": "Input tokens per call. A large context sent repeatedly is the biggest cost.", "col.tokens": "Tokens",

    "tools.title": "{agent}: tools", "tools.explain": "Tool calls across all history.", "tools.shell": "Most used shell commands", "tools.shell.explain": "First word of each command.",
    "gf.explain": "Graphify doesn't record tokens saved. The panel shows where a graph exists and how often the agents used it.",
    "gf.projects": "Projects with a graph", "gf.calls": "Recorded calls", "gf.none": "none", "col.folder": "Folder", "col.size": "Size", "col.updated": "Updated",
    "ol.title": "Ollama (local models)", "ol.explain": "Ollama doesn't write tokens to its logs, only requests and how long each took. Tokens show up when it's used through OpenCode.",
    "ol.reqs": "Requests", "ol.time": "Generation time", "ol.errors": "{n} with errors", "ol.viaOC": "Tokens via OpenCode", "ol.installed": "Installed models", "ol.loaded": "loaded now: {m}", "ol.none": "none loaded now",

    "tips.title": "What you can optimize", "tips.explain": "Computed from your data for the selected period.", "tips.nothing": "Nothing to suggest for this period.",
    "level.high": "High priority", "level.medium": "Medium priority", "level.low": "Suggestion", "level.ok": "Info",
    "d.codexRtk.t": "Codex barely goes through RTK",
    "d.codexRtk.p": "{Period} Codex made {n} calls and only {r} of its commands were filtered by RTK. {pct} of Codex's shell commands are PowerShell (Get-Content, Get-ChildItem…), which RTK doesn't compress. Every file read that way lands in the context in full.",
    "d.codexRtk.a": "Tell Codex in AGENTS.md to use rg, cat and ls through Git Bash (or rtk read / rtk grep) instead of Get-Content and Select-String.",
    "d.rate.t": "Codex uses {pct} of its 5-hour window per hour on average",
    "d.rate.p": "At this pace the 5-hour window runs out in {dur}{overrun}. The {plan} plan is the bottleneck: Codex reads a large context every turn{ctx}.",
    "d.rate.overrun": "; {n} of the last {m} windows hit 100%", "d.rate.ctx": " (average of {n} input tokens per call)",
    "d.rate.a": "Use Codex for short, well-scoped tasks and leave long sessions to Claude Code. To cut per-turn cost: a smaller model for simple tasks and fresh sessions more often.",
    "d.cache.t": "Codex reuses less cache than Claude Code",
    "d.cache.p": "{a} of Codex input comes from cache, versus {b} in Claude Code. Uncached input counts in full against the limit.",
    "d.cache.a": "Avoid switching model or reasoning level mid-session and avoid editing AGENTS.md while working: both invalidate the cache.",
    "d.opus.t": "{pct} of Claude Code runs on Opus",
    "d.opus.p": "Sonnet 5.5 costs half per token (US$ 2/10 vs. US$ 4/20 for Opus 5.5). At API prices, Opus added up to {usd} {period}.",
    "d.opus.a": "Use Sonnet for search and reading subagents (Explore) and mechanical tasks; keep Opus for planning and hard code.",
    "d.ctx.t": "Claude Code average context: {n} tokens per call",
    "d.ctx.p": "Every call resends the whole conversation history. Even with cache, very long sessions weigh on the limit.",
    "d.ctx.a": "Start new sessions when you switch topics and use /compact once a conversation passes ~200k tokens.",
    "d.sess.t1": "1 session went over 50 million tokens", "d.sess.tn": "{n} sessions went over 50 million tokens",
    "d.sess.p": "The largest: {proj} ({agent}), {tok} tokens in {n} calls.",
    "d.sess.a": "See the Projects & sessions tab. Sessions like these are usually wait loops or tasks that could be split up.",
    "d.waits.t": "{n} wait-tool calls in Claude Code",
    "d.waits.p": "Each wait call ({list}) resends the whole context to the model just to check whether something finished.",
    "d.waits.a": "Prefer long waits (bigger timeout) or run the process in the background and get notified when it ends, instead of polling status in a loop.",
    "d.failure.t": "RTK fails on \"{cmd}\" ({n} times)",
    "d.failure.p": "The command still runs, but uncompressed and with the overhead of trying to filter first.",
    "d.failure.a": "Add \"{cmd}\" to exclude_commands in the [hooks] section of RTK's config.toml, or report the case to the RTK project.",
    "d.noGain.t": "Commands RTK rewrites without reducing anything",
    "d.noGain.item": "{cmd} ({pct} no gain over {n} runs)",
    "d.noGain.a": "Normal for outputs that are already short. If any of these has long output, compare with rtk bypass to check the filter.",
    "d.hr.t1": "Headroom compressed only {pct} of what went through it", "d.hr.t0": "The Headroom proxy had no traffic in this period",
    "d.hr.p1": "The last request through the proxy was {when}. Otherwise the agents talk to the API directly and Headroom does nothing.", "d.hr.p0": "No requests recorded by the proxy.",
    "d.hr.a": "Run headroom doctor to check that the proxy is up and the agents point to it. If it isn't worth it, turn it off so it doesn't add latency.",
    "d.gf.t": "Graphify is barely being used",
    "d.gf.p": "Only {n} project(s) have a graph and the agents called Graphify {c} time(s). Without a graph, the agent reads whole files to understand the code.",
    "d.gf.a": "Build the graph for the large projects you use most (see the Projects & sessions tab) and remind the agent to check it before opening files.",
    "d.share.t": "{agent} accounts for {pct} of new tokens", "d.share.p": "Breakdown {period}: {list}.",

    "sources.title": "Where the data comes from", "col.tool": "Tool", "col.file": "File", "col.status": "Status", "col.read": "Read",
    "sources.ok": "ok", "sources.no": "not found",
    "sources.claude": "{n} session files", "sources.codex": "{n} sessions, {m} limit readings", "sources.opencode": "{n} model responses", "sources.ollama": "{n} generation requests", "sources.rtk": "{n} commands", "sources.headroom": "{n} savings events", "sources.graphify": "{n} projects with a graph",
    "sources.note": "Collected in {s} s. Everything is read locally and nothing leaves this machine. \"API equivalent\" prices live in <code>prices.json</code>; you can fill in models that have no price there.",
  },

  // ---------------------------------------------------------------- Spanish
  es: {
    app: "Token Economy",
    "period.label": "Período",
    "period.today": "Hoy", "period.24h": "24 h", "period.7d": "7 días", "period.30d": "30 días", "period.all": "Todo",
    "period.name.today": "hoy", "period.name.24h": "en las últimas 24 h", "period.name.7d": "en los últimos 7 días", "period.name.30d": "en los últimos 30 días", "period.name.all": "en todo el historial",
    "btn.refresh": "Actualizar", "btn.refresh.hint": "Volver a leer los datos ahora", "btn.reading": "Leyendo…", "btn.theme": "Cambiar tema claro/oscuro", "language": "Idioma",
    "tab.overview": "Resumen", "tab.limits": "Límites del plan", "tab.models": "Agentes y modelos", "tab.savings": "Ahorro", "tab.projects": "Proyectos y sesiones", "tab.tools": "Herramientas", "tab.tips": "Qué optimizar", "tab.sources": "Fuentes",
    "loading.title": "Leyendo los registros de los agentes…", "loading.sub": "La primera vez lee todo el historial. Después, solo lo que cambió.", "loading.offline": "El servidor no responde. Vuelve a abrir Token Economy.", "loading.error": "Error: {msg}",
    "header.data": "datos de {when} · se actualiza cada minuto", "header.loading": "cargando…",
    "agent.claude": "Claude Code", "agent.codex": "Codex", "agent.opencode": "OpenCode", "agent.ollama": "Ollama", "agent.unknown": "Sin identificar",
    "proj.~none": "(sin carpeta)", "proj.~temp": "(carpeta temporal)",
    "empty": "Sin datos en este período.", "no.charts": "Gráficos no disponibles: sin acceso a cdnjs.cloudflare.com.", "sort": "Ordenar",
    "now": "ahora", "days": "{n} días",

    "overview.daily": "Tokens nuevos por día", "overview.daily.explain": "Entrada sin caché + escritura en caché + salida. Es lo que más pesa en el límite. La lectura de caché queda fuera porque cuesta ~10% del precio.", "overview.byHour": "por hora", "overview.byDay": "por día",
    "overview.consumes": "Quién consume más", "overview.consumes.explain": "Parte de cada agente en los tokens nuevos del período.",
    "overview.saves": "Quién ahorra más", "overview.saves.explain": "Tokens que no entraron en el contexto gracias a RTK y Headroom.",
    "kpi.new": "Tokens nuevos", "kpi.new.det": "{n} llamadas al modelo {period}", "kpi.new.hint": "Entrada sin caché + escritura en caché + salida",
    "kpi.cache": "Leídos de caché", "kpi.cache.det": "{pct} de la entrada vino de la caché", "kpi.cache.hint": "La lectura de caché cuesta cerca del 10% del precio normal",
    "kpi.api": "Equivalente en API", "kpi.api.unpriced": "{n} tokens sin precio", "kpi.api.table": "a precio de lista", "kpi.api.hint": "Lo que costaría pagando por token. Con suscripción, lo que limita es la ventana de 5 h y la semanal.",
    "kpi.rtk": "Ahorro de RTK", "kpi.rtk.det": "{pct} de la salida de {n} comandos", "kpi.rtk.hint": "Tokens de salida de comandos que no entraron en el contexto",
    "kpi.hr": "Ahorro de Headroom", "kpi.hr.det": "{n} solicitudes por el proxy", "kpi.hr.hint": "Tokens comprimidos por el proxy de Headroom",
    "calls": "{n} llamadas",

    "lim.codex5h": "Codex: ventana de 5 horas", "lim.codexWeek": "Codex: límite semanal", "lim.plan": "plan {p}",
    "lim.chart": "Uso de la ventana de 5 h de Codex en el tiempo", "lim.chart.explain": "Cada caída a cero es una ventana nueva. Una pendiente fuerte = límite que se gasta rápido.",
    "lim.windows": "Ventanas de 5 h recientes de Codex", "lim.claude": "Claude: límites", "lim.last5h": "Tokens en las últimas 5 horas", "lim.last5h.explain": "Comparación directa del volumen reciente de cada agente.",
    "lim.noCodex": "Codex aún no registró límites.",
    "lim.resets": "Se reinicia", "lim.free": "ninguna ventana en curso", "lim.rate": "Ritmo de esta ventana", "lim.perHour": "{pct} por hora", "lim.perDay": "{pct} por día",
    "lim.fullIn": "A este ritmo, 100% en", "lim.avgRate": "Ritmo medio (últimas 10 ventanas)", "lim.lastReading": "Última lectura",
    "lim.weekRate": "Ritmo de la semana", "lim.weekEnd": "A este ritmo, fin de semana en", "lim.weekReadings": "Lecturas esta semana",
    "lim.series5h": "Ventana de 5 h", "lim.seriesWeek": "Semanal",
    "st.reached": "Límite alcanzado", "st.willRunOut": "Se agotará antes del reinicio", "st.attention": "Atención", "st.calm": "Todo bien",
    "col.windowStart": "Inicio de la ventana", "col.used": "Usado", "col.rate": "Ritmo (%/h)", "col.wouldRunOut": "Se agotaría en", "col.wouldRunOut.hint": "Tiempo hasta llegar al 100% manteniendo el ritmo de la ventana", "col.lastReading": "Última lectura",
    "lim.claude.5h": "La ventana de 5 h se reinicia", "lim.claude.no": "Semanal", "lim.claude.source": "Fuente", "lim.claude.headroom": "Headroom, {when}",
    "lim.claude.noData": "Claude Code no guarda el porcentaje de sus límites en sus registros. Headroom puede leerlo mientras su proxy está encendido", "lim.claude.stale": ", pero la última lectura es del {date} ({when}), demasiado antigua para confiar en ella",
    "lim.claude.usage": "Para ver el número exacto ahora, escribe <b>/usage</b> en Claude Code. Abajo, el volumen reciente de tokens sirve de termómetro.",
    "lim.peak": "{pct} de tu pico de 5 h", "lim.peak.hint": "{n} llamadas · pico de 5 h en los últimos 30 días: {peak}", "lim.peak.explain": "\"Pico\" es la ventana de 5 h con más tokens nuevos en los últimos 30 días.",

    "mod.table": "Consumo por agente y modelo", "mod.table.explain": "\"Entrada/llamada\" muestra el peso medio de cada llamada: un contexto grande repetido es el gasto principal. \"Caché\" es la parte de la entrada servida desde la caché (cuanto mayor, más barato).",
    "mod.perHour": "Tokens nuevos en el tiempo", "mod.composition": "Composición de la entrada", "mod.composition.explain": "Cómo arma cada agente el contexto que envía al modelo.",
    "mod.hourOfDay": "Horario de uso", "mod.hourOfDay.explain": "Tokens nuevos por hora del día, sumando el período.",
    "col.agent": "Agente", "col.model": "Modelo", "col.calls": "Llamadas", "col.new": "Tokens nuevos", "col.inputPerCall": "Entrada/llamada", "col.inputPerCall.hint": "Tamaño medio del contexto enviado en cada llamada",
    "col.cache": "Caché", "col.cache.hint": "Parte de la entrada leída de la caché", "col.outputPerCall": "Salida/llamada", "col.reasoning": "Razonamiento", "col.reasoning.hint": "Tokens de razonamiento informados (solo Codex y OpenCode los registran)", "col.api": "Equivalente API", "unpriced": "sin precio",
    "comp.cr": "Lectura de caché", "comp.cw": "Escritura en caché", "comp.input": "Entrada sin caché", "comp.out": "Salida",

    "sav.perDay": "Ahorro por día", "sav.rtkCmd": "RTK por comando", "sav.rtkCmd.explain": "Comandos que más pasaron por RTK. \"Sin ganancia\" cuenta las veces en que el filtro no redujo nada.",
    "sav.hook": "Cobertura del hook de RTK", "sav.hook.explain": "Decisiones del hook en Claude Code. Solo los comandos de shell pasan por él.",
    "sav.failures": "Fallos de RTK", "sav.failures.explain": "Comandos que RTK no pudo filtrar y ejecutó sin compresión.", "sav.failures.total": "{n} fallos en todo el historial. Cuando falla, el comando se ejecuta normal, solo que sin compresión.",
    "sav.headroom": "Headroom por cliente y modelo",
    "kpi.rtkSaved": "RTK: tokens ahorrados", "kpi.rtkSaved.det": "{pct} de la salida de comandos", "kpi.rtkCmds": "RTK: comandos filtrados", "kpi.rtkCmds.det": "{n} salidas enormes fuera de la cuenta", "kpi.rtkCmds.hint": "RTK no cuenta salidas de más de 7.500 tokens, que el agente recortaría de todos modos",
    "kpi.hrSaved": "Headroom: tokens ahorrados", "kpi.hrSaved.det": "{pct} de lo que pasó por el proxy", "kpi.hrSaved.reqs": "{n} solicitudes",
    "kpi.savTotal": "Ahorro sobre el consumo", "kpi.savTotal.det": "tus herramientas respecto a los tokens nuevos", "kpi.savTotal.hint": "Cuánto mayores habrían sido los tokens nuevos sin tus herramientas de ahorro. Aproximado: RTK estima los tokens como bytes ÷ 4.",
    "col.command": "Comando", "col.runs": "Veces", "col.saved": "Tokens ahorrados", "col.reduction": "Reducción", "col.reduction.hint": "Solo eventos que registran el tamaño original", "col.noGain": "Sin ganancia",
    "dec.defer": "Reescrito a RTK", "dec.ask": "Reescrito, pidiendo permiso", "dec.allow": "Permitido sin reescribir", "dec.deny": "Bloqueado",
    "sav.attrib": "Agente de cada comando de RTK: {a} identificado por el texto del comando, {b} por el agente activo en ese momento, {c} sin identificar.",
    "col.client": "Cliente", "col.reqs": "Solicitudes", "col.usdSaved": "US$ ahorrados",

    "proj.top": "Proyectos que más consumen", "proj.sessions": "Sesiones más pesadas",
    "col.project": "Proyecto", "col.agents": "Agentes", "col.tokensCache": "Tokens (con caché)", "col.share": "Parte", "col.start": "Inicio", "col.duration": "Duración", "col.avgCtx": "Contexto medio", "col.avgCtx.hint": "Tokens de entrada por llamada. Un contexto grande repetido es lo que más gasta.", "col.tokens": "Tokens",

    "tools.title": "{agent}: herramientas", "tools.explain": "Llamadas a herramientas en todo el historial.", "tools.shell": "Comandos de shell más usados", "tools.shell.explain": "Primera palabra de cada comando.",
    "gf.explain": "Graphify no registra los tokens ahorrados. El panel muestra dónde hay un grafo listo y cuántas veces lo usaron los agentes.",
    "gf.projects": "Proyectos con grafo", "gf.calls": "Llamadas registradas", "gf.none": "ninguna", "col.folder": "Carpeta", "col.size": "Tamaño", "col.updated": "Actualizado",
    "ol.title": "Ollama (modelos locales)", "ol.explain": "Ollama no guarda tokens en sus registros, solo las solicitudes y cuánto tardó cada una. Los tokens aparecen cuando se usa desde OpenCode.",
    "ol.reqs": "Solicitudes", "ol.time": "Tiempo de generación", "ol.errors": "{n} con error", "ol.viaOC": "Tokens vía OpenCode", "ol.installed": "Modelos instalados", "ol.loaded": "cargado ahora: {m}", "ol.none": "ninguno cargado ahora",

    "tips.title": "Qué se puede optimizar", "tips.explain": "Calculado a partir de tus datos del período seleccionado.", "tips.nothing": "Nada que sugerir con los datos del período.",
    "level.high": "Prioridad alta", "level.medium": "Prioridad media", "level.low": "Sugerencia", "level.ok": "Información",
    "d.codexRtk.t": "Codex casi no pasa por RTK",
    "d.codexRtk.p": "{Period} Codex hizo {n} llamadas y solo {r} de sus comandos pasaron por el filtro de RTK. El {pct} de los comandos de shell de Codex son PowerShell (Get-Content, Get-ChildItem…), que RTK no comprime. Cada archivo leído así entra completo en el contexto.",
    "d.codexRtk.a": "Pide a Codex, en AGENTS.md, que use rg, cat y ls desde Git Bash (o rtk read / rtk grep) en lugar de Get-Content y Select-String.",
    "d.rate.t": "Codex gasta en promedio el {pct} de la ventana de 5 h por hora",
    "d.rate.p": "A este ritmo la ventana de 5 h se agota en {dur}{overrun}. El plan {plan} es el cuello de botella: Codex lee un contexto grande en cada turno{ctx}.",
    "d.rate.overrun": "; {n} de las últimas {m} ventanas llegaron al 100%", "d.rate.ctx": " (promedio de {n} tokens de entrada por llamada)",
    "d.rate.a": "Usa Codex para tareas cortas y bien delimitadas y deja las sesiones largas para Claude Code. Para gastar menos por turno: un modelo más pequeño en tareas simples y sesiones nuevas con más frecuencia.",
    "d.cache.t": "Codex reaprovecha menos caché que Claude Code",
    "d.cache.p": "El {a} de la entrada de Codex viene de la caché, frente al {b} en Claude Code. La entrada sin caché cuenta completa en el límite.",
    "d.cache.a": "Evita cambiar de modelo o de nivel de razonamiento a mitad de sesión y evita editar AGENTS.md mientras trabajas: ambas cosas invalidan la caché.",
    "d.opus.t": "El {pct} de Claude Code funciona con Opus",
    "d.opus.p": "Sonnet 5.5 cuesta la mitad por token (US$ 2/10 frente a US$ 4/20 de Opus 5.5). A precio de API, Opus sumó {usd} {period}.",
    "d.opus.a": "Usa Sonnet para subagentes de búsqueda y lectura (Explore) y tareas mecánicas; deja Opus para planificar y para el código difícil.",
    "d.ctx.t": "Contexto medio de Claude Code: {n} tokens por llamada",
    "d.ctx.p": "Cada llamada reenvía todo el historial de la conversación. Incluso con caché, las sesiones muy largas pesan en el límite.",
    "d.ctx.a": "Empieza sesiones nuevas al cambiar de tema y usa /compact cuando la conversación pase de ~200 mil tokens.",
    "d.sess.t1": "1 sesión superó los 50 millones de tokens", "d.sess.tn": "{n} sesiones superaron los 50 millones de tokens",
    "d.sess.p": "La mayor: {proj} ({agent}), {tok} tokens en {n} llamadas.",
    "d.sess.a": "Mira la pestaña Proyectos y sesiones. Sesiones así suelen ser bucles de espera o tareas que se podrían dividir.",
    "d.waits.t": "{n} llamadas a herramientas de espera en Claude Code",
    "d.waits.p": "Cada llamada de espera ({list}) reenvía todo el contexto al modelo solo para comprobar si algo terminó.",
    "d.waits.a": "Prefiere esperas largas (timeout mayor) o ejecutar el proceso en segundo plano y recibir un aviso al final, en lugar de consultar el estado en bucle.",
    "d.failure.t": "RTK falla en \"{cmd}\" ({n} veces)",
    "d.failure.p": "El comando se sigue ejecutando, pero sin compresión y con el costo de intentar filtrarlo antes.",
    "d.failure.a": "Añade \"{cmd}\" a exclude_commands en la sección [hooks] del config.toml de RTK, o reporta el caso al proyecto RTK.",
    "d.noGain.t": "Comandos que RTK reescribe sin reducir nada",
    "d.noGain.item": "{cmd} ({pct} sin ganancia en {n} ejecuciones)",
    "d.noGain.a": "Es normal en salidas que ya son cortas. Si alguno tiene salida larga, compáralo con rtk bypass para revisar el filtro.",
    "d.hr.t1": "Headroom comprimió solo el {pct} de lo que pasó por él", "d.hr.t0": "El proxy de Headroom no tuvo tráfico en el período",
    "d.hr.p1": "La última solicitud por el proxy fue {when}. Fuera de eso, los agentes hablan directo con la API y Headroom no actúa.", "d.hr.p0": "No hay solicitudes registradas por el proxy.",
    "d.hr.a": "Ejecuta headroom doctor para ver si el proxy está activo y si los agentes apuntan a él. Si no compensa, apágalo para no sumar latencia.",
    "d.gf.t": "Graphify casi no se está usando",
    "d.gf.p": "Solo {n} proyecto(s) tienen grafo y los agentes llamaron a Graphify {c} vez/veces. Sin grafo, el agente lee archivos completos para entender el código.",
    "d.gf.a": "Genera el grafo en los proyectos grandes que más usas (mira la pestaña Proyectos y sesiones) y recuerda al agente consultarlo antes de abrir archivos.",
    "d.share.t": "{agent} representa el {pct} de los tokens nuevos", "d.share.p": "Distribución {period}: {list}.",

    "sources.title": "De dónde vienen los datos", "col.tool": "Herramienta", "col.file": "Archivo", "col.status": "Estado", "col.read": "Leído",
    "sources.ok": "ok", "sources.no": "no encontrado",
    "sources.claude": "{n} archivos de sesión", "sources.codex": "{n} sesiones, {m} lecturas de límite", "sources.opencode": "{n} respuestas del modelo", "sources.ollama": "{n} solicitudes de generación", "sources.rtk": "{n} comandos", "sources.headroom": "{n} eventos de ahorro", "sources.graphify": "{n} proyectos con grafo",
    "sources.note": "Recolección hecha en {s} s. Todo se lee localmente y nada sale de esta máquina. Los precios del \"equivalente en API\" están en <code>prices.json</code>; ahí puedes completar los modelos sin precio.",
  },
};

let LANG = "pt";

function detectLanguage() {
  try {
    // "painel.idioma": key used before the English translation
    const saved = localStorage.getItem("panel.language") ?? localStorage.getItem("painel.idioma");
    if (saved && TXT[saved]) return saved;
  } catch { /* no storage */ }
  const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
  return TXT[nav] ? nav : "en";
}

function t(key, vars) {
  let s = TXT[LANG]?.[key] ?? TXT.en[key] ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? vars[k] : m));
  return s;
}

// applies the translations to the elements with data-i18n / data-i18n-title / data-i18n-aria
function translatePage() {
  document.documentElement.lang = LOCALES[LANG];
  document.title = t("app");
  document.querySelectorAll("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
  document.querySelectorAll("[data-i18n-title]").forEach((el) => (el.title = t(el.dataset.i18nTitle)));
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
}

// ---------------------------------------------------------------- texts added later
Object.assign(TXT.pt, {
  "unit.label": "Unidade", "unit.tokens": "Tokens", "unit.usd": "US$",
  "unit.hint": "Mostrar em tokens ou no que custaria pela API",
  "overview.daily.usd": "Custo equivalente em API por dia", "overview.daily.usd.explain": "Quanto o uso de cada dia custaria pagando por token na API, com cache incluído. Na assinatura você não paga isso, mas dá a medida do valor que está usando.",
  "overview.consumes.usd.explain": "Parte de cada agente no custo equivalente em API do período.",
  "overview.saves.usd.explain": "Quanto o RTK e o Headroom pouparam em dólar, pelo preço da API.",
  "kpi.savUsd": "Economia em US$", "kpi.savUsd.det": "RTK {rtk} · Headroom {hr}", "kpi.savUsd.hint": "Valor em API dos tokens que o RTK e o Headroom tiraram do contexto. O RTK conta só a primeira leitura (estimativa mínima): sem ele, a saída ainda seria relida do cache nas chamadas seguintes.",
  "kpi.rtk.usd": "≈ {usd} pelo preço da API",
  "sav.perDay.usd": "Economia por dia (US$)", "sav.perDay.tokens": "Economia por dia (tokens)",
  "col.usdSavedMin": "US$ poupados (mín.)", "col.usdSavedMin.hint": "Pelo preço de entrada do modelo do agente. Conta só a primeira leitura.",
  "ai.title": "Análise por IA", "ai.explain": "Uma IA à sua escolha lê o resumo dos seus dados (números por agente, modelo, comando e projeto, nunca o conteúdo das conversas) e diz o que otimizar. Compara com o período anterior e com a última análise. Usa a sua assinatura ou a sua chave, então gasta alguns milhares de tokens.",
  "ai.use": "Usar", "ai.cli": "Ferramentas instaladas", "ai.api": "API (compatível com OpenAI)", "ai.custom": "Comando personalizado", "ai.noCli": "Nenhuma CLI conhecida encontrada no PATH",
  "ai.model": "Modelo", "ai.model.ph": "padrão da ferramenta", "ai.model.required": "obrigatório",
  "ai.url": "URL base", "ai.key": "Chave da API", "ai.key.ph": "sk-… ou $NOME_DA_VARIAVEL", "ai.key.saved": "salva neste computador (deixe vazio para manter)",
  "ai.command": "Comando", "ai.command.ph": "minha-ia --prompt-file {file}", "ai.command.hint": "Use {file} para receber o caminho do prompt; sem ele, o prompt vai pela entrada padrão.",
  "ai.days": "Período", "ai.days.n": "{n} dias", "ai.analyze": "Analisar com IA", "ai.viewPrompt": "Ver o que é enviado", "ai.unverified": "comando não testado; ajuste em ai_providers.json se falhar",
  "ai.running": "Analisando… {stage} ({s} s)", "ai.error": "A análise falhou: {msg}", "ai.none": "Nenhuma análise ainda. Escolha a IA e clique em Analisar com IA.",
  "ai.done": "Análise de {date} por {by}{model} · {days} dias · {s} s", "ai.score": "Nota de otimização", "ai.previous": "Análises anteriores",
  "rules.title": "Regras automáticas", "rules.explain": "Recalculadas a cada minuto por regras fixas do código, sem IA e sem custo.",
  "prices.title": "Preços", "prices.explain": "Os valores em US$ usam tabelas públicas de preço, atualizadas sozinhas toda semana. Seus ajustes em prices.json têm prioridade.",
  "prices.source.manual": "Seus ajustes (prices.json)", "prices.source.litellm": "LiteLLM (tabela pública)", "prices.source.openrouter": "OpenRouter (catálogo público)", "prices.source.default": "Tabela embutida (sem internet)",
  "prices.models": "{n} modelos", "prices.updated": "atualizado {when}", "prices.refresh": "Atualizar preços", "prices.unpriced": "Modelos sem preço: {list}. Adicione em prices.json.", "prices.all": "Todos os modelos usados têm preço.",
  "col.source": "Fonte", "col.input": "Entrada", "col.output": "Saída", "col.cacheRead": "Leitura de cache", "prices.byModel": "Preço usado para cada modelo (US$ por 1 milhão de tokens)",
  "sources.note": "Coleta feita em {s} s. Os registros são lidos localmente e nada deles sai da máquina.",
});
Object.assign(TXT.en, {
  "unit.label": "Unit", "unit.tokens": "Tokens", "unit.usd": "US$",
  "unit.hint": "Show tokens or what it would cost on the API",
  "overview.daily.usd": "API-equivalent cost per day", "overview.daily.usd.explain": "What each day's usage would cost paying per token on the API, cache included. On a subscription you don't pay this, but it shows the value you're using.",
  "overview.consumes.usd.explain": "Each agent's share of the API-equivalent cost in the period.",
  "overview.saves.usd.explain": "How much RTK and Headroom saved in dollars, at API prices.",
  "kpi.savUsd": "Savings in US$", "kpi.savUsd.det": "RTK {rtk} · Headroom {hr}", "kpi.savUsd.hint": "API value of the tokens RTK and Headroom kept out of the context. RTK counts only the first read (a minimum estimate): without it, the output would still be re-read from cache on later calls.",
  "kpi.rtk.usd": "≈ {usd} at API prices",
  "sav.perDay.usd": "Savings per day (US$)", "sav.perDay.tokens": "Savings per day (tokens)",
  "col.usdSavedMin": "US$ saved (min.)", "col.usdSavedMin.hint": "At the input price of the agent's model. Counts only the first read.",
  "ai.title": "AI analysis", "ai.explain": "An AI of your choice reads a summary of your data (numbers per agent, model, command and project, never the content of your conversations) and tells you what to optimize. It compares with the previous period and with the last analysis. It runs on your subscription or your key, so it uses a few thousand tokens.",
  "ai.use": "Use", "ai.cli": "Installed tools", "ai.api": "API (OpenAI-compatible)", "ai.custom": "Custom command", "ai.noCli": "No known CLI found on PATH",
  "ai.model": "Model", "ai.model.ph": "tool default", "ai.model.required": "required",
  "ai.url": "Base URL", "ai.key": "API key", "ai.key.ph": "sk-… or $ENV_VAR_NAME", "ai.key.saved": "saved on this computer (leave empty to keep it)",
  "ai.command": "Command", "ai.command.ph": "my-ai --prompt-file {file}", "ai.command.hint": "Use {file} to receive the prompt file path; without it, the prompt goes through standard input.",
  "ai.days": "Period", "ai.days.n": "{n} days", "ai.analyze": "Analyze with AI", "ai.viewPrompt": "See what is sent", "ai.unverified": "untested command; adjust ai_providers.json if it fails",
  "ai.running": "Analyzing… {stage} ({s} s)", "ai.error": "The analysis failed: {msg}", "ai.none": "No analysis yet. Pick an AI and click Analyze with AI.",
  "ai.done": "Analysis from {date} by {by}{model} · {days} days · {s} s", "ai.score": "Optimization score", "ai.previous": "Previous analyses",
  "rules.title": "Automatic rules", "rules.explain": "Recomputed every minute by fixed rules in the code, with no AI and no cost.",
  "prices.title": "Prices", "prices.explain": "US$ values use public price tables that update themselves every week. Your overrides in prices.json win.",
  "prices.source.manual": "Your overrides (prices.json)", "prices.source.litellm": "LiteLLM (public table)", "prices.source.openrouter": "OpenRouter (public catalog)", "prices.source.default": "Built-in table (offline)",
  "prices.models": "{n} models", "prices.updated": "updated {when}", "prices.refresh": "Update prices", "prices.unpriced": "Models without a price: {list}. Add them to prices.json.", "prices.all": "Every model in use has a price.",
  "col.source": "Source", "col.input": "Input", "col.output": "Output", "col.cacheRead": "Cache read", "prices.byModel": "Price used for each model (US$ per 1 million tokens)",
  "sources.note": "Collected in {s} s. Logs are read locally and nothing from them leaves this machine.",
});
Object.assign(TXT.es, {
  "unit.label": "Unidad", "unit.tokens": "Tokens", "unit.usd": "US$",
  "unit.hint": "Mostrar en tokens o en lo que costaría por la API",
  "overview.daily.usd": "Costo equivalente en API por día", "overview.daily.usd.explain": "Lo que costaría el uso de cada día pagando por token en la API, con la caché incluida. Con suscripción no pagas esto, pero da la medida del valor que estás usando.",
  "overview.consumes.usd.explain": "Parte de cada agente en el costo equivalente en API del período.",
  "overview.saves.usd.explain": "Cuánto ahorraron RTK y Headroom en dólares, a precio de API.",
  "kpi.savUsd": "Ahorro en US$", "kpi.savUsd.det": "RTK {rtk} · Headroom {hr}", "kpi.savUsd.hint": "Valor en API de los tokens que RTK y Headroom sacaron del contexto. RTK cuenta solo la primera lectura (estimación mínima): sin él, la salida se seguiría releyendo de la caché en las llamadas siguientes.",
  "kpi.rtk.usd": "≈ {usd} a precio de API",
  "sav.perDay.usd": "Ahorro por día (US$)", "sav.perDay.tokens": "Ahorro por día (tokens)",
  "col.usdSavedMin": "US$ ahorrados (mín.)", "col.usdSavedMin.hint": "Al precio de entrada del modelo del agente. Cuenta solo la primera lectura.",
  "ai.title": "Análisis con IA", "ai.explain": "Una IA que elijas lee un resumen de tus datos (números por agente, modelo, comando y proyecto, nunca el contenido de tus conversaciones) y te dice qué optimizar. Compara con el período anterior y con el último análisis. Usa tu suscripción o tu clave, así que gasta algunos miles de tokens.",
  "ai.use": "Usar", "ai.cli": "Herramientas instaladas", "ai.api": "API (compatible con OpenAI)", "ai.custom": "Comando personalizado", "ai.noCli": "No se encontró ninguna CLI conocida en el PATH",
  "ai.model": "Modelo", "ai.model.ph": "predeterminado de la herramienta", "ai.model.required": "obligatorio",
  "ai.url": "URL base", "ai.key": "Clave de API", "ai.key.ph": "sk-… o $NOMBRE_DE_VARIABLE", "ai.key.saved": "guardada en este equipo (déjala vacía para mantenerla)",
  "ai.command": "Comando", "ai.command.ph": "mi-ia --prompt-file {file}", "ai.command.hint": "Usa {file} para recibir la ruta del prompt; sin él, el prompt va por la entrada estándar.",
  "ai.days": "Período", "ai.days.n": "{n} días", "ai.analyze": "Analizar con IA", "ai.viewPrompt": "Ver lo que se envía", "ai.unverified": "comando sin probar; ajusta ai_providers.json si falla",
  "ai.running": "Analizando… {stage} ({s} s)", "ai.error": "El análisis falló: {msg}", "ai.none": "Aún no hay análisis. Elige la IA y pulsa Analizar con IA.",
  "ai.done": "Análisis del {date} por {by}{model} · {days} días · {s} s", "ai.score": "Nota de optimización", "ai.previous": "Análisis anteriores",
  "rules.title": "Reglas automáticas", "rules.explain": "Se recalculan cada minuto con reglas fijas del código, sin IA y sin costo.",
  "prices.title": "Precios", "prices.explain": "Los valores en US$ usan tablas públicas de precios que se actualizan solas cada semana. Tus ajustes en prices.json tienen prioridad.",
  "prices.source.manual": "Tus ajustes (prices.json)", "prices.source.litellm": "LiteLLM (tabla pública)", "prices.source.openrouter": "OpenRouter (catálogo público)", "prices.source.default": "Tabla incluida (sin internet)",
  "prices.models": "{n} modelos", "prices.updated": "actualizado {when}", "prices.refresh": "Actualizar precios", "prices.unpriced": "Modelos sin precio: {list}. Añádelos en prices.json.", "prices.all": "Todos los modelos usados tienen precio.",
  "col.source": "Fuente", "col.input": "Entrada", "col.output": "Salida", "col.cacheRead": "Lectura de caché", "prices.byModel": "Precio usado para cada modelo (US$ por 1 millón de tokens)",
  "sources.note": "Recolección hecha en {s} s. Los registros se leen localmente y nada de ellos sale de esta máquina.",
});

// ---------------------------------------------------------------- summary, score and subscriptions
Object.assign(TXT.pt, {
  "tab.summary": "Resumo", "tab.overview": "Consumo", "tab.sources": "Ajustes e fontes",
  "summary.score": "Nota de otimização", "summary.score.view": "Ver como subir a nota", "summary.score.gain": "+{p} pts com {criterion}",
  "summary.value": "Quanto vale o seu uso", "summary.value.paid": "Você pagou (assinaturas)", "summary.value.api": "Valeria pela API", "summary.value.sav": "Poupado pelo RTK e Headroom",
  "summary.value.mult": "Seu uso {period} valeria {x}× o que você pagou.", "summary.value.noSubs": "Cadastre suas assinaturas em Ajustes para comparar com o que você paga.",
  "summary.limits": "Limites agora", "summary.limits.no": "Nenhum agente registrou limites.", "summary.pie": "Uso por agente", "summary.days": "Uso ao longo do período",
  "summary.insights": "Principais pontos", "summary.insights.view": "Ver todos", "source.ai": "IA", "source.auto": "Automático",
  "score.title": "Como a nota é calculada", "score.explain": "A nota soma critérios que você consegue mudar. Cada critério vale alguns pontos: bateu a meta, ganha todos; chegou ao limite ruim, zera; no meio, proporcional. Chegar a 100 é possível.",
  "score.yours": "Seu valor", "score.target": "Meta", "score.bad": "Zera em", "score.points": "{p} de {max} pts", "score.excluded": "Fora da nota por falta de dados: {list}.",
  "score.c.context.t": "Tamanho do contexto", "score.c.context.o": "Tokens de entrada por chamada, em média. Cada chamada reenvia o histórico inteiro.", "score.c.context.a": "Abra sessões novas ao trocar de tarefa e use /compact quando a conversa crescer.",
  "score.c.sessions.t": "Sessões longas", "score.c.sessions.o": "Parte das chamadas feitas em sessões com mais de {limit} chamadas.", "score.c.sessions.a": "Divida o trabalho em sessões menores e guarde o estado num arquivo de notas em vez de manter a conversa viva.",
  "score.c.cache.t": "Aproveitamento do cache", "score.c.cache.o": "Parte da entrada lida do cache, que custa cerca de 10% do preço normal.", "score.c.cache.a": "Evite trocar de modelo ou editar arquivos de instrução no meio da sessão: isso invalida o cache.",
  "score.c.model.t": "Escolha do modelo", "score.c.model.o": "Parte dos tokens novos em modelos de ponta (US$ 4 ou mais por milhão). Os mais usados: {models}.", "score.c.model.a": "Use modelos menores em subagentes, buscas e tarefas mecânicas; deixe o de ponta para planejar e para o código difícil.",
  "score.c.rtk.t": "Cobertura do RTK", "score.c.rtk.o": "Dos comandos que o RTK sabe comprimir, quantos passaram por ele. {bypassed} escaparam, a maioria PowerShell.", "score.c.rtk.a": "Peça aos agentes comandos de Bash (cat, rg, ls) em vez de Get-Content, Select-String e Get-ChildItem.",
  "score.c.waits.t": "Chamadas de espera", "score.c.waits.o": "Parte das chamadas de ferramenta que só esperam algo terminar. Cada uma reenvia o contexto inteiro.", "score.c.waits.a": "Use esperas longas ou rode o processo em segundo plano com aviso no fim, em vez de consultar em laço.",
  "score.c.limits.t": "Ritmo nos limites", "score.c.limits.o": "Parte das janelas de 5 h do Codex que chegaram a 95% ({maxed_out} de {windows}).", "score.c.limits.a": "Distribua o uso do Codex ao longo do dia e use modelos mais leves nas tarefas simples.",
  "subs.title": "Assinaturas", "subs.explain": "Valor mensal de cada assinatura, em US$. O painel calcula a parte proporcional do período escolhido e compara com o valor do uso pela API.",
  "subs.name": "Nome", "subs.agent": "Agente", "subs.monthly": "US$ por mês", "subs.add": "Adicionar assinatura", "subs.save": "Salvar", "subs.saved": "Salvo", "subs.remove": "Remover", "subs.other": "Outro / vários",
  "kpi.rtk.usd2": "≈ {est} pelo preço da API (mínimo {min})", "col.usdEst": "US$ poupados (estimado)", "col.usdEst.hint": "Conta a saída poupada e as vezes que ela seria relida do cache até sair do contexto.",
  "kpi.savUsd.hint": "Valor em API dos tokens que o RTK e o Headroom tiraram do contexto. Para o RTK, conta também as releituras do cache até a saída sair do contexto; o mínimo, que conta uma leitura só, aparece no detalhe.",
});
Object.assign(TXT.en, {
  "tab.summary": "Summary", "tab.overview": "Usage", "tab.sources": "Settings & sources",
  "summary.score": "Optimization score", "summary.score.view": "See how to raise it", "summary.score.gain": "+{p} pts from {criterion}",
  "summary.value": "What your usage is worth", "summary.value.paid": "You paid (subscriptions)", "summary.value.api": "Worth on the API", "summary.value.sav": "Saved by RTK and Headroom",
  "summary.value.mult": "Your usage {period} would be worth {x}× what you paid.", "summary.value.noSubs": "Add your subscriptions in Settings to compare with what you pay.",
  "summary.limits": "Limits now", "summary.limits.no": "No agent has recorded limits.", "summary.pie": "Usage by agent", "summary.days": "Usage over the period",
  "summary.insights": "Key points", "summary.insights.view": "See all", "source.ai": "AI", "source.auto": "Automatic",
  "score.title": "How the score works", "score.explain": "The score adds up criteria you can change. Each one is worth some points: hit the target and you get them all; reach the bad limit and you get zero; in between, proportional. Reaching 100 is possible.",
  "score.yours": "Your value", "score.target": "Target", "score.bad": "Zero at", "score.points": "{p} of {max} pts", "score.excluded": "Left out for lack of data: {list}.",
  "score.c.context.t": "Context size", "score.c.context.o": "Average input tokens per call. Every call resends the whole history.", "score.c.context.a": "Start new sessions when you switch tasks and use /compact when the conversation grows.",
  "score.c.sessions.t": "Long sessions", "score.c.sessions.o": "Share of calls made in sessions with more than {limit} calls.", "score.c.sessions.a": "Split work into smaller sessions and keep state in a notes file instead of keeping the conversation alive.",
  "score.c.cache.t": "Cache use", "score.c.cache.o": "Share of input read from cache, which costs about 10% of the normal price.", "score.c.cache.a": "Avoid switching models or editing instruction files mid-session: both invalidate the cache.",
  "score.c.model.t": "Model choice", "score.c.model.o": "Share of new tokens on top-tier models (US$ 4+ per million). Most used: {models}.", "score.c.model.a": "Use smaller models for subagents, searches and mechanical tasks; keep the top tier for planning and hard code.",
  "score.c.rtk.t": "RTK coverage", "score.c.rtk.o": "Of the commands RTK knows how to compress, how many went through it. {bypassed} slipped past, mostly PowerShell.", "score.c.rtk.a": "Ask agents for Bash commands (cat, rg, ls) instead of Get-Content, Select-String and Get-ChildItem.",
  "score.c.waits.t": "Wait calls", "score.c.waits.o": "Share of tool calls that only wait for something to finish. Each resends the whole context.", "score.c.waits.a": "Use long waits or run the process in the background with a notification, instead of polling in a loop.",
  "score.c.limits.t": "Limit pacing", "score.c.limits.o": "Share of Codex 5-hour windows that reached 95% ({maxed_out} of {windows}).", "score.c.limits.a": "Spread Codex use across the day and use lighter models for simple tasks.",
  "subs.title": "Subscriptions", "subs.explain": "Monthly price of each subscription, in US$. The panel prorates it to the selected period and compares it with what the usage is worth on the API.",
  "subs.name": "Name", "subs.agent": "Agent", "subs.monthly": "US$ per month", "subs.add": "Add subscription", "subs.save": "Save", "subs.saved": "Saved", "subs.remove": "Remove", "subs.other": "Other / several",
  "kpi.rtk.usd2": "≈ {est} at API prices (minimum {min})", "col.usdEst": "US$ saved (estimated)", "col.usdEst.hint": "Counts the saved output plus the times it would be re-read from cache until it leaves the context.",
  "kpi.savUsd.hint": "API value of the tokens RTK and Headroom kept out of the context. For RTK it also counts cache re-reads until the output leaves the context; the minimum, counting a single read, is in the detail.",
});
Object.assign(TXT.es, {
  "tab.summary": "Resumen", "tab.overview": "Consumo", "tab.sources": "Ajustes y fuentes",
  "summary.score": "Nota de optimización", "summary.score.view": "Ver cómo subir la nota", "summary.score.gain": "+{p} pts con {criterion}",
  "summary.value": "Cuánto vale tu uso", "summary.value.paid": "Pagaste (suscripciones)", "summary.value.api": "Valdría por la API", "summary.value.sav": "Ahorrado por RTK y Headroom",
  "summary.value.mult": "Tu uso {period} valdría {x}× lo que pagaste.", "summary.value.noSubs": "Registra tus suscripciones en Ajustes para compararlas con lo que pagas.",
  "summary.limits": "Límites ahora", "summary.limits.no": "Ningún agente registró límites.", "summary.pie": "Uso por agente", "summary.days": "Uso a lo largo del período",
  "summary.insights": "Puntos principales", "summary.insights.view": "Ver todos", "source.ai": "IA", "source.auto": "Automático",
  "score.title": "Cómo se calcula la nota", "score.explain": "La nota suma criterios que puedes cambiar. Cada criterio vale algunos puntos: si alcanzas la meta, los ganas todos; si llegas al límite malo, cero; en medio, proporcional. Llegar a 100 es posible.",
  "score.yours": "Tu valor", "score.target": "Meta", "score.bad": "Cero en", "score.points": "{p} de {max} pts", "score.excluded": "Fuera de la nota por falta de datos: {list}.",
  "score.c.context.t": "Tamaño del contexto", "score.c.context.o": "Tokens de entrada por llamada, en promedio. Cada llamada reenvía todo el historial.", "score.c.context.a": "Abre sesiones nuevas al cambiar de tarea y usa /compact cuando la conversación crezca.",
  "score.c.sessions.t": "Sesiones largas", "score.c.sessions.o": "Parte de las llamadas hechas en sesiones con más de {limit} llamadas.", "score.c.sessions.a": "Divide el trabajo en sesiones más pequeñas y guarda el estado en un archivo de notas en lugar de mantener viva la conversación.",
  "score.c.cache.t": "Aprovechamiento de la caché", "score.c.cache.o": "Parte de la entrada leída de la caché, que cuesta cerca del 10% del precio normal.", "score.c.cache.a": "Evita cambiar de modelo o editar archivos de instrucciones a mitad de sesión: invalida la caché.",
  "score.c.model.t": "Elección del modelo", "score.c.model.o": "Parte de los tokens nuevos en modelos de gama alta (US$ 4 o más por millón). Los más usados: {models}.", "score.c.model.a": "Usa modelos más pequeños en subagentes, búsquedas y tareas mecánicas; deja el de gama alta para planificar y para el código difícil.",
  "score.c.rtk.t": "Cobertura de RTK", "score.c.rtk.o": "De los comandos que RTK sabe comprimir, cuántos pasaron por él. {bypassed} se escaparon, casi todos de PowerShell.", "score.c.rtk.a": "Pide a los agentes comandos de Bash (cat, rg, ls) en lugar de Get-Content, Select-String y Get-ChildItem.",
  "score.c.waits.t": "Llamadas de espera", "score.c.waits.o": "Parte de las llamadas a herramientas que solo esperan a que algo termine. Cada una reenvía todo el contexto.", "score.c.waits.a": "Usa esperas largas o ejecuta el proceso en segundo plano con aviso al final, en lugar de consultar en bucle.",
  "score.c.limits.t": "Ritmo en los límites", "score.c.limits.o": "Parte de las ventanas de 5 h de Codex que llegaron al 95% ({maxed_out} de {windows}).", "score.c.limits.a": "Reparte el uso de Codex a lo largo del día y usa modelos más ligeros en las tareas simples.",
  "subs.title": "Suscripciones", "subs.explain": "Precio mensual de cada suscripción, en US$. El panel calcula la parte proporcional del período elegido y la compara con lo que vale el uso por la API.",
  "subs.name": "Nombre", "subs.agent": "Agente", "subs.monthly": "US$ por mes", "subs.add": "Añadir suscripción", "subs.save": "Guardar", "subs.saved": "Guardado", "subs.remove": "Quitar", "subs.other": "Otro / varios",
  "kpi.rtk.usd2": "≈ {est} a precio de API (mínimo {min})", "col.usdEst": "US$ ahorrados (estimado)", "col.usdEst.hint": "Cuenta la salida ahorrada y las veces que se releería de la caché hasta salir del contexto.",
  "kpi.savUsd.hint": "Valor en API de los tokens que RTK y Headroom sacaron del contexto. Para RTK cuenta también las relecturas de la caché hasta que la salida sale del contexto; el mínimo, con una sola lectura, aparece en el detalle.",
});

// ---------------------------------------------------------------- limit windows of all agents
Object.assign(TXT.pt, {
  "win.five_hour": "Janela de 5 h", "win.seven_day": "Semanal", "win.seven_day_opus": "Semanal · Opus", "win.seven_day_sonnet": "Semanal · Sonnet", "win.seven_day_fable": "Semanal · Fable",
  "win.plan": "plano {p}", "win.resets": "zera em {dur}", "win.free": "nenhuma janela em curso",
  "win.runsOut": "Nesse ritmo acaba em {dur}, antes de zerar", "win.reaches": "Nesse ritmo chega a {pct} quando zerar", "win.rate": "{pct} por hora",
  "win.title": "Todas as janelas de limite", "win.explain": "Só as janelas que o seu plano tem, com o ritmo atual e a previsão até zerar. Vêm dos endpoints oficiais de uso da Anthropic e da OpenAI, com o login que cada CLI já guarda; sem eles, o Codex usa os próprios registros.",
  "win.read": "lido {when}",
  "lim.claude.error.no_login": "Não achei o login do Claude Code nesta máquina. Entre no Claude Code para ver os limites aqui.",
  "lim.claude.error.login_expired": "O login do Claude Code venceu. Abra o Claude Code uma vez para ele renovar.",
  "lim.claude.error.disabled": "A leitura dos limites do Claude está desligada em Ajustes.",
  "lim.claude.error.other": "Não consegui ler os limites do Claude ({error}).",
  "settings.limits": "Limites do Claude", "settings.limits.explain": "O Token Economy usa o login que o Claude Code já guarda neste computador para consultar o endpoint oficial de uso da Anthropic, como fazem o Headroom e o ccassist. O token só vai para a Anthropic e não é gravado nem mostrado.", "settings.limits.enable": "Ler os limites do Claude pela conta logada no Claude Code",
});
Object.assign(TXT.en, {
  "win.five_hour": "5-hour window", "win.seven_day": "Weekly", "win.seven_day_opus": "Weekly · Opus", "win.seven_day_sonnet": "Weekly · Sonnet", "win.seven_day_fable": "Weekly · Fable",
  "win.plan": "{p} plan", "win.resets": "resets in {dur}", "win.free": "no window in progress",
  "win.runsOut": "At this pace it runs out in {dur}, before the reset", "win.reaches": "At this pace it reaches {pct} at the reset", "win.rate": "{pct} per hour",
  "win.title": "All limit windows", "win.explain": "Only the windows your plan has, with the current pace and a forecast until it resets. They come from Anthropic's and OpenAI's official usage endpoints, using the login each CLI already keeps; without them, Codex falls back to its own logs.",
  "win.read": "read {when}",
  "lim.claude.error.no_login": "No Claude Code login found on this machine. Sign in to Claude Code to see its limits here.",
  "lim.claude.error.login_expired": "The Claude Code login expired. Open Claude Code once so it renews.",
  "lim.claude.error.disabled": "Reading Claude limits is turned off in Settings.",
  "lim.claude.error.other": "Couldn't read Claude limits ({error}).",
  "settings.limits": "Claude limits", "settings.limits.explain": "Token Economy uses the login Claude Code already keeps on this computer to query Anthropic's official usage endpoint, the same way Headroom and ccassist do. The token goes only to Anthropic and is never saved or shown.", "settings.limits.enable": "Read Claude limits using the Claude Code login",
});
Object.assign(TXT.es, {
  "win.five_hour": "Ventana de 5 h", "win.seven_day": "Semanal", "win.seven_day_opus": "Semanal · Opus", "win.seven_day_sonnet": "Semanal · Sonnet", "win.seven_day_fable": "Semanal · Fable",
  "win.plan": "plan {p}", "win.resets": "se reinicia en {dur}", "win.free": "ninguna ventana en curso",
  "win.runsOut": "A este ritmo se agota en {dur}, antes del reinicio", "win.reaches": "A este ritmo llega al {pct} en el reinicio", "win.rate": "{pct} por hora",
  "win.title": "Todas las ventanas de límite", "win.explain": "Solo las ventanas que tiene tu plan, con el ritmo actual y la previsión hasta el reinicio. Vienen de los endpoints oficiales de uso de Anthropic y OpenAI, con la sesión que cada CLI ya guarda; sin ellos, Codex usa sus propios registros.",
  "win.read": "leído {when}",
  "lim.claude.error.no_login": "No encontré el inicio de sesión de Claude Code en esta máquina. Entra en Claude Code para ver sus límites aquí.",
  "lim.claude.error.login_expired": "La sesión de Claude Code venció. Abre Claude Code una vez para que se renueve.",
  "lim.claude.error.disabled": "La lectura de los límites de Claude está desactivada en Ajustes.",
  "lim.claude.error.other": "No pude leer los límites de Claude ({error}).",
  "settings.limits": "Límites de Claude", "settings.limits.explain": "Token Economy usa la sesión que Claude Code ya guarda en este equipo para consultar el endpoint oficial de uso de Anthropic, como hacen Headroom y ccassist. El token solo va a Anthropic y nunca se guarda ni se muestra.", "settings.limits.enable": "Leer los límites de Claude con la sesión de Claude Code",
});

// ---------------------------------------------------------------- credits and version notice
Object.assign(TXT.pt, {
  "cred.title": "Créditos de uso extra do Claude", "cred.usage": "US$ {used} usados de US$ {limit} no mês", "cred.left": "Sobram US$ {left}",
  "cred.disabled": "O uso extra está desligado no seu plano.", "cred.noLimit": "US$ {used} usados no mês (sem limite definido)",
  "win.restart": "O app ainda está com a versão antiga do servidor. Clique com o botão direito no ícone da bandeja, escolha Sair e abra o Token Economy de novo.",
});
Object.assign(TXT.en, {
  "cred.title": "Claude extra-usage credits", "cred.usage": "US$ {used} used of US$ {limit} this month", "cred.left": "US$ {left} left",
  "cred.disabled": "Extra usage is turned off on your plan.", "cred.noLimit": "US$ {used} used this month (no limit set)",
  "win.restart": "The app is still running the old server version. Right-click the tray icon, choose Quit and open Token Economy again.",
});
Object.assign(TXT.es, {
  "cred.title": "Créditos de uso extra de Claude", "cred.usage": "US$ {used} usados de US$ {limit} este mes", "cred.left": "Quedan US$ {left}",
  "cred.disabled": "El uso extra está desactivado en tu plan.", "cred.noLimit": "US$ {used} usados este mes (sin límite definido)",
  "win.restart": "La app sigue con la versión antigua del servidor. Haz clic derecho en el icono de la bandeja, elige Salir y vuelve a abrir Token Economy.",
});

// ---------------------------------------------------------------- cloud session credits
Object.assign(TXT.pt, { "cloud.title": "Créditos de nuvem do Claude Code", "cloud.left": "Sobram US$ {left} de US$ {limit}", "cloud.renews": "renova em {dur}", "cloud.locked": "bloqueado" });
Object.assign(TXT.en, { "cloud.title": "Claude Code cloud credits", "cloud.left": "US$ {left} left of US$ {limit}", "cloud.renews": "renews in {dur}", "cloud.locked": "locked" });
Object.assign(TXT.es, { "cloud.title": "Créditos de nube de Claude Code", "cloud.left": "Quedan US$ {left} de US$ {limit}", "cloud.renews": "se renueva en {dur}", "cloud.locked": "bloqueado" });

Object.assign(TXT.pt, { "lim.history": "Histórico dos limites", "lim.windows": "Janelas de 5 h recentes",
  "lim.chart.explain": "Uma cor por agente; linha cheia = janela de 5 h, tracejada = semanal, pontilhada = semanal por modelo. Cada queda a zero é uma janela nova; inclinação forte = limite gasto rápido. Clique na legenda para esconder ou mostrar uma linha.",
  "lim.history.empty": "Nenhuma leitura de limite neste período. Os limites aparecem quando o agente informa o uso do plano (Claude Code e Codex fazem isso)." });
Object.assign(TXT.en, { "lim.history": "Limit history", "lim.windows": "Recent 5-hour windows",
  "lim.chart.explain": "One color per agent; solid line = 5-hour window, dashed = weekly, dotted = weekly per model. Each drop to zero is a new window; a steep slope means the limit is going fast. Click the legend to hide or show a line.",
  "lim.history.empty": "No limit readings in this period. Limits show up when the agent reports plan usage (Claude Code and Codex do)." });
Object.assign(TXT.es, { "lim.history": "Historial de límites", "lim.windows": "Ventanas de 5 h recientes",
  "lim.chart.explain": "Un color por agente; línea continua = ventana de 5 h, discontinua = semanal, punteada = semanal por modelo. Cada caída a cero es una ventana nueva; una pendiente fuerte = límite que se gasta rápido. Haz clic en la leyenda para ocultar o mostrar una línea.",
  "lim.history.empty": "No hay lecturas de límite en este período. Los límites aparecen cuando el agente informa el uso del plan (Claude Code y Codex lo hacen)." });

// ---------------------------------------------------------------- detected token-saving tools
Object.assign(TXT.pt, {
  "sav.mine": "Suas ferramentas de economia", "sav.mine.explain": "Só aparecem as ferramentas encontradas neste computador. As que registram quanto economizam mostram tokens e US$; as que não registram mostram o que dá para saber, sem inventar números.",
  "sav.none": "Nenhuma ferramenta de economia de tokens foi encontrada neste computador.",
  "sav.tokensSaved": "tokens poupados {period}", "sav.noEvents": "sem economia registrada {period}",
  "sav.notMeasured": "Não registra quanto economiza", "sav.doesNotMeasure": "A ferramenta não grava a economia, então o painel não estima.",
  "sav.calls": "Usada {n} vezes pelos agentes (histórico)",
  "sav.agents": "Agentes: {list}", "sav.kompact": "desde que o proxy iniciou · {n} requisições",
  "sav.kpi.tools": "Ferramentas encontradas", "sav.kpi.tools.det": "{m} com medição · {s} sem medição",
  "sav.kpi.tokens": "Tokens poupados", "sav.kpi.min": "mínimo {min}", "sav.kpi.byTools": "por {n} ferramenta(s)",
  "cat.command_output": "saída de comandos", "cat.proxy": "proxy de API", "cat.code_index": "índice de código", "cat.response_style": "estilo de resposta", "cat.memory": "memória e contexto", "cat.other": "outra",
  "overview.saves.explain": "Tokens que suas ferramentas de economia tiraram do contexto.", "overview.saves.usd.explain": "Quanto suas ferramentas de economia pouparam em dólar, pelo preço da API.",
  "summary.value.sav": "Poupado pelas suas ferramentas",
});
Object.assign(TXT.en, {
  "sav.mine": "Your token-saving tools", "sav.mine.explain": "Only tools found on this computer are shown. Tools that record their savings show tokens and US$; the others show what can be known, with no made-up numbers.",
  "sav.none": "No token-saving tool was found on this computer.",
  "sav.tokensSaved": "tokens saved {period}", "sav.noEvents": "no savings recorded {period}",
  "sav.notMeasured": "Doesn't record its savings", "sav.doesNotMeasure": "The tool doesn't store its savings, so the panel doesn't estimate them.",
  "sav.calls": "Used {n} times by your agents (all history)",
  "sav.agents": "Agents: {list}", "sav.kompact": "since the proxy started · {n} requests",
  "sav.kpi.tools": "Tools found", "sav.kpi.tools.det": "{m} measured · {s} not measured",
  "sav.kpi.tokens": "Tokens saved", "sav.kpi.min": "minimum {min}", "sav.kpi.byTools": "by {n} tool(s)",
  "cat.command_output": "command output", "cat.proxy": "API proxy", "cat.code_index": "code index", "cat.response_style": "response style", "cat.memory": "memory & context", "cat.other": "other",
  "overview.saves.explain": "Tokens your token-saving tools kept out of the context.", "overview.saves.usd.explain": "How much your token-saving tools saved in dollars, at API prices.",
  "summary.value.sav": "Saved by your tools",
});
Object.assign(TXT.es, {
  "sav.mine": "Tus herramientas de ahorro", "sav.mine.explain": "Solo aparecen las herramientas encontradas en este equipo. Las que registran cuánto ahorran muestran tokens y US$; las demás muestran lo que se puede saber, sin inventar números.",
  "sav.none": "No se encontró ninguna herramienta de ahorro de tokens en este equipo.",
  "sav.tokensSaved": "tokens ahorrados {period}", "sav.noEvents": "sin ahorro registrado {period}",
  "sav.notMeasured": "No registra cuánto ahorra", "sav.doesNotMeasure": "La herramienta no guarda su ahorro, así que el panel no lo estima.",
  "sav.calls": "Usada {n} veces por los agentes (historial)",
  "sav.agents": "Agentes: {list}", "sav.kompact": "desde que se inició el proxy · {n} solicitudes",
  "sav.kpi.tools": "Herramientas encontradas", "sav.kpi.tools.det": "{m} con medición · {s} sin medición",
  "sav.kpi.tokens": "Tokens ahorrados", "sav.kpi.min": "mínimo {min}", "sav.kpi.byTools": "por {n} herramienta(s)",
  "cat.command_output": "salida de comandos", "cat.proxy": "proxy de API", "cat.code_index": "índice de código", "cat.response_style": "estilo de respuesta", "cat.memory": "memoria y contexto", "cat.other": "otra",
  "overview.saves.explain": "Tokens que tus herramientas de ahorro sacaron del contexto.", "overview.saves.usd.explain": "Cuánto ahorraron tus herramientas en dólares, a precio de API.",
  "summary.value.sav": "Ahorrado por tus herramientas",
});

// ---------------------------------------------------------------- unmeasured tools: usage per project
Object.assign(TXT.pt, {
  "sav.projects": "Configurada em {p} projeto(s) · consultada em {u}",
  "sav.proj": "Onde as ferramentas sem medição trabalham",
  "sav.proj.explain": "Estas ferramentas não gravam quanto economizam. Para você ter uma ideia do proveito, a tabela mostra em que projetos cada uma está configurada e quantas vezes os agentes a consultaram em cada um (chamadas pelo MCP ou pela skill e execuções do programa no terminal, em todo o histórico).",
  "col.setUp": "Configurada no projeto", "col.queries": "Consultas", "sav.yes": "sim", "sav.no": "não",
});
Object.assign(TXT.en, {
  "sav.projects": "Set up in {p} project(s) · queried in {u}",
  "sav.proj": "Where your unmeasured tools are working",
  "sav.proj.explain": "These tools don't record how much they save. To give you a sense of what you get from them, the table shows which projects each one is set up in and how often your agents queried it there (MCP or skill calls and runs of its program in the terminal, across all history).",
  "col.setUp": "Set up in project", "col.queries": "Queries", "sav.yes": "yes", "sav.no": "no",
});
Object.assign(TXT.es, {
  "sav.projects": "Configurada en {p} proyecto(s) · consultada en {u}",
  "sav.proj": "Dónde trabajan las herramientas sin medición",
  "sav.proj.explain": "Estas herramientas no registran cuánto ahorran. Para que tengas una idea del provecho, la tabla muestra en qué proyectos está configurada cada una y cuántas veces la consultaron los agentes en cada uno (llamadas por MCP o skill y ejecuciones del programa en la terminal, en todo el historial).",
  "col.setUp": "Configurada en el proyecto", "col.queries": "Consultas", "sav.yes": "sí", "sav.no": "no",
});

// ---------------------------------------------------------------- demo mode (python server.py --demo)
Object.assign(TXT.pt, {
  "header.demo": "Dados de demonstração",
  "header.demo.hint": "Dados fictícios gerados por python server.py --demo. Nada aqui vem desta máquina.",
  "ai.demo": "No modo de demonstração a análise por IA não roda. A análise abaixo é um exemplo fictício.",
});
Object.assign(TXT.en, {
  "header.demo": "Demo data",
  "header.demo.hint": "Fictional data generated by python server.py --demo. Nothing here comes from this machine.",
  "ai.demo": "AI analysis doesn't run in demo mode. The analysis below is a fictional example.",
});
Object.assign(TXT.es, {
  "header.demo": "Datos de demostración",
  "header.demo.hint": "Datos ficticios generados por python server.py --demo. Nada de esto viene de esta máquina.",
  "ai.demo": "En el modo de demostración el análisis por IA no se ejecuta. El análisis de abajo es un ejemplo ficticio.",
});

LANG = detectLanguage();

// updates and donations (Settings)
Object.assign(TXT.pt, {
  "update.title": "Atualizações", "update.check": "Procurar atualizações", "update.current": "Versão {v}",
  "update.uptodate": "Você está na versão mais recente.", "update.none": "Ainda não há versão publicada no GitHub.",
  "update.available": "Versão {v} disponível.", "update.notes": "Novidades", "update.install": "Atualizar agora",
  "update.installing": "Atualizando…", "update.done": "Atualizado para a versão {v}. Reinicie o Token Economy (ícone da bandeja > Sair e abra de novo) para usar a versão nova.",
  "update.error": "Não deu para verificar agora ({e}).", "update.local_changes": "Você alterou arquivos do app; atualize com git pull no terminal.",
  "update.demo": "No modo demo não há atualização.", "update.failed": "A atualização falhou: {e}",
  "update.via.git": "Instalação via git: atualiza para a versão publicada (tag).", "update.via.zip": "Instalação via ZIP: baixa a versão do GitHub e mantém suas configurações (.cache).",
  "donate.title": "Apoie o projeto", "donate.explain": "O Token Economy é gratuito. Se ele te ajuda, qualquer apoio ajuda a mantê-lo. Uma estrela no GitHub e sugestões também valem muito.",
  "donate.sponsors": "Apoiar no GitHub Sponsors", "donate.star": "Dar uma estrela no GitHub", "donate.copy": "Copiar", "donate.copied": "Copiado",
  "donate.lightning": "Lightning (sats, BOLT12)", "donate.monero": "Monero (XMR)",
});
Object.assign(TXT.en, {
  "update.title": "Updates", "update.check": "Check for updates", "update.current": "Version {v}",
  "update.uptodate": "You have the latest version.", "update.none": "No version has been published on GitHub yet.",
  "update.available": "Version {v} is available.", "update.notes": "What's new", "update.install": "Update now",
  "update.installing": "Updating…", "update.done": "Updated to version {v}. Restart Token Economy (tray icon > Quit, then open it again) to use it.",
  "update.error": "Couldn't check right now ({e}).", "update.local_changes": "You changed the app's files; update with git pull in a terminal.",
  "update.demo": "Updates are off in demo mode.", "update.failed": "The update failed: {e}",
  "update.via.git": "Installed with git: updates to the published version (tag).", "update.via.zip": "Installed from a ZIP: downloads the version from GitHub and keeps your settings (.cache).",
  "donate.title": "Support the project", "donate.explain": "Token Economy is free. If it helps you, any support helps keep it going. A star on GitHub and suggestions count a lot too.",
  "donate.sponsors": "Sponsor on GitHub", "donate.star": "Star on GitHub", "donate.copy": "Copy", "donate.copied": "Copied",
  "donate.lightning": "Lightning (sats, BOLT12)", "donate.monero": "Monero (XMR)",
});
Object.assign(TXT.es, {
  "update.title": "Actualizaciones", "update.check": "Buscar actualizaciones", "update.current": "Versión {v}",
  "update.uptodate": "Tienes la versión más reciente.", "update.none": "Todavía no hay ninguna versión publicada en GitHub.",
  "update.available": "La versión {v} está disponible.", "update.notes": "Novedades", "update.install": "Actualizar ahora",
  "update.installing": "Actualizando…", "update.done": "Actualizado a la versión {v}. Reinicia Token Economy (ícono de la bandeja > Salir y ábrelo de nuevo) para usarla.",
  "update.error": "No se pudo verificar ahora ({e}).", "update.local_changes": "Cambiaste archivos de la app; actualiza con git pull en una terminal.",
  "update.demo": "En el modo demo no hay actualizaciones.", "update.failed": "La actualización falló: {e}",
  "update.via.git": "Instalado con git: actualiza a la versión publicada (tag).", "update.via.zip": "Instalado desde un ZIP: descarga la versión de GitHub y conserva tu configuración (.cache).",
  "donate.title": "Apoya el proyecto", "donate.explain": "Token Economy es gratuito. Si te ayuda, cualquier apoyo ayuda a mantenerlo. Una estrella en GitHub y las sugerencias también cuentan mucho.",
  "donate.sponsors": "Patrocinar en GitHub Sponsors", "donate.star": "Dar una estrella en GitHub", "donate.copy": "Copiar", "donate.copied": "Copiado",
  "donate.lightning": "Lightning (sats, BOLT12)", "donate.monero": "Monero (XMR)",
});

// ---------------------------------------------------------------- tools you can add
Object.assign(TXT.pt, {
  "add.title": "Ferramentas que você pode adicionar",
  "add.explain": "Projetos gratuitos e de código aberto de outros desenvolvedores, que reduzem os tokens que seus agentes gastam. Escolha uma por tipo: duas do mesmo tipo podem disputar o mesmo hook. Depois de instalar, ela aparece aqui sozinha na próxima coleta.",
  "add.gap": "você ainda não tem", "add.have": "você já tem uma deste tipo",
  "add.more": "Outras alternativas (tipos que você já cobre)",
  "add.measured": "o painel mostra a economia", "add.usage": "o painel mostra o uso",
  "add.works": "Funciona com: {list}", "add.license": "Licença: {l}", "add.noWindows": "não roda no Windows", "add.external": "precisa de serviço externo ou chave de API",
  "add.seeRepo": "Instalação: veja o README do projeto.", "add.readme": "Ler o README antes de instalar",
  "add.disclaimer": "O Token Economy não é ligado a esses projetos. Os comandos vêm do README de cada um; confira lá antes de rodar.",
  "add.cat.command_output": "Encurtam a saída de comandos (testes, git, builds, logs) antes que o agente leia. É onde costuma ir a maior parte dos tokens.",
  "add.cat.code_index": "Indexam o código do projeto para o agente perguntar onde está cada coisa, em vez de abrir e varrer arquivos inteiros.",
  "add.cat.proxy": "Ficam entre o agente e a API e comprimem o que é enviado em cada requisição.",
  "add.cat.memory": "Guardam o que foi feito em sessões anteriores para o agente não precisar redescobrir tudo.",
  "add.cat.response_style": "Fazem o agente responder de forma mais curta, poupando tokens de saída.",
  "d.add.command_output.t": "Nada está encurtando a saída dos comandos",
  "d.add.command_output.p": "Seus agentes leem a saída completa de testes, git e builds. Ferramentas como {list} cortam o que é repetido antes de chegar ao modelo.",
  "d.add.code_index.t": "Nenhum índice de código instalado",
  "d.add.code_index.p": "Sem índice, o agente abre e varre arquivos para achar o que procura. Ferramentas como {list} respondem isso com bem menos tokens.",
  "d.add.a": "Veja as opções, o que cada uma faz e o comando de instalação em Economia > Ferramentas que você pode adicionar.",
});
Object.assign(TXT.en, {
  "add.title": "Tools you can add",
  "add.explain": "Free, open-source projects by other developers that cut the tokens your agents spend. Pick one per kind: two of the same kind can fight over the same hook. Once installed, it shows up here by itself on the next collection.",
  "add.gap": "you don't have one yet", "add.have": "you already have one of this kind",
  "add.more": "Other alternatives (kinds you already cover)",
  "add.measured": "panel shows its savings", "add.usage": "panel shows its usage",
  "add.works": "Works with: {list}", "add.license": "License: {l}", "add.noWindows": "doesn't run on Windows", "add.external": "needs an external service or API key",
  "add.seeRepo": "Install: see the project's README.", "add.readme": "Read the README before installing",
  "add.disclaimer": "Token Economy isn't affiliated with these projects. The commands come from each project's README; check there before running them.",
  "add.cat.command_output": "Shorten command output (tests, git, builds, logs) before the agent reads it. This is usually where most tokens go.",
  "add.cat.code_index": "Index the project's code so the agent can ask where things are instead of opening and scanning whole files.",
  "add.cat.proxy": "Sit between the agent and the API and compress what each request sends.",
  "add.cat.memory": "Keep what was done in earlier sessions so the agent doesn't have to rediscover it.",
  "add.cat.response_style": "Make the agent answer more briefly, saving output tokens.",
  "d.add.command_output.t": "Nothing is shortening command output",
  "d.add.command_output.p": "Your agents read the full output of tests, git and builds. Tools such as {list} cut the repetitive parts before they reach the model.",
  "d.add.code_index.t": "No code index installed",
  "d.add.code_index.p": "Without an index, the agent opens and scans files to find what it needs. Tools such as {list} answer that with far fewer tokens.",
  "d.add.a": "See the options, what each does and its install command in Savings > Tools you can add.",
});
Object.assign(TXT.es, {
  "add.title": "Herramientas que puedes añadir",
  "add.explain": "Proyectos gratuitos y de código abierto de otros desarrolladores que reducen los tokens que gastan tus agentes. Elige una por tipo: dos del mismo tipo pueden competir por el mismo hook. Una vez instalada, aparece aquí sola en la siguiente recolección.",
  "add.gap": "aún no tienes ninguna", "add.have": "ya tienes una de este tipo",
  "add.more": "Otras alternativas (tipos que ya cubres)",
  "add.measured": "el panel muestra el ahorro", "add.usage": "el panel muestra el uso",
  "add.works": "Funciona con: {list}", "add.license": "Licencia: {l}", "add.noWindows": "no funciona en Windows", "add.external": "necesita un servicio externo o clave de API",
  "add.seeRepo": "Instalación: consulta el README del proyecto.", "add.readme": "Leer el README antes de instalar",
  "add.disclaimer": "Token Economy no está vinculado a estos proyectos. Los comandos vienen del README de cada uno; revísalo antes de ejecutarlos.",
  "add.cat.command_output": "Acortan la salida de los comandos (tests, git, builds, logs) antes de que el agente la lea. Suele ser donde se van más tokens.",
  "add.cat.code_index": "Indexan el código del proyecto para que el agente pregunte dónde está cada cosa en vez de abrir y recorrer archivos enteros.",
  "add.cat.proxy": "Se ponen entre el agente y la API y comprimen lo que se envía en cada petición.",
  "add.cat.memory": "Guardan lo hecho en sesiones anteriores para que el agente no tenga que redescubrirlo.",
  "add.cat.response_style": "Hacen que el agente responda más breve, ahorrando tokens de salida.",
  "d.add.command_output.t": "Nada está acortando la salida de los comandos",
  "d.add.command_output.p": "Tus agentes leen la salida completa de tests, git y builds. Herramientas como {list} recortan lo repetido antes de que llegue al modelo.",
  "d.add.code_index.t": "No hay ningún índice de código instalado",
  "d.add.code_index.p": "Sin índice, el agente abre y recorre archivos para encontrar lo que busca. Herramientas como {list} lo resuelven con muchos menos tokens.",
  "d.add.a": "Mira las opciones, qué hace cada una y su comando de instalación en Ahorro > Herramientas que puedes añadir.",
});

// ---------------------------------------------------------------- updates of the installed tools
Object.assign(TXT.pt, {
  "upd.current": "Versão {v} (a mais recente)",
  "upd.available": "Atualização disponível: {a} → {b}",
  "upd.copyPrompt": "Copiar instrução para o seu agente",
  "upd.prompt": "Atualize o {name} da versão {a} para a {b}. Ele está instalado em {path}.\nAntes, leia as notas da versão em {url}/releases e me avise se houver mudança que quebre algo.\nComando oficial de atualização (se ele foi instalado de outro jeito, como npm, pip, uv, cargo ou instalador, use o método que corresponde a esse caminho):\n{steps}\nDepois confirme com `{check}` e me diga a versão instalada.",
  "upd.prompt.noCmd": "  (o projeto não traz comando de atualização; siga o README em {url})",
  "d.upd.t": "{n} ferramenta(s) de economia com versão nova",
  "d.upd.a": "Em Economia, cada uma mostra o comando de atualização e um botão que copia a instrução para você colar no seu agente.",
});
Object.assign(TXT.en, {
  "upd.current": "Version {v} (latest)",
  "upd.available": "Update available: {a} → {b}",
  "upd.copyPrompt": "Copy instruction for your agent",
  "upd.prompt": "Update {name} from version {a} to {b}. It is installed at {path}.\nFirst read the release notes at {url}/releases and tell me about any breaking change.\nOfficial update command (if it was installed some other way, such as npm, pip, uv, cargo or an installer, use the method that matches that path):\n{steps}\nThen confirm with `{check}` and tell me the installed version.",
  "upd.prompt.noCmd": "  (the project gives no update command; follow the README at {url})",
  "d.upd.t": "{n} token-saving tool(s) have a new version",
  "d.upd.a": "In Savings, each one shows its update command and a button that copies an instruction to paste into your agent.",
});
Object.assign(TXT.es, {
  "upd.current": "Versión {v} (la más reciente)",
  "upd.available": "Actualización disponible: {a} → {b}",
  "upd.copyPrompt": "Copiar instrucción para tu agente",
  "upd.prompt": "Actualiza {name} de la versión {a} a la {b}. Está instalado en {path}.\nAntes, lee las notas de la versión en {url}/releases y avísame si hay algún cambio que rompa algo.\nComando oficial de actualización (si se instaló de otra forma, como npm, pip, uv, cargo o un instalador, usa el método que corresponda a esa ruta):\n{steps}\nDespués confirma con `{check}` y dime la versión instalada.",
  "upd.prompt.noCmd": "  (el proyecto no trae comando de actualización; sigue el README en {url})",
  "d.upd.t": "{n} herramienta(s) de ahorro con versión nueva",
  "d.upd.a": "En Ahorro, cada una muestra su comando de actualización y un botón que copia la instrucción para pegarla en tu agente.",
});
