# Token Economy

A local dashboard and Windows tray app that shows how many tokens your AI coding agents use and how much your token-saving tools save. Available in English, Portuguese and Spanish.

[Leia em português](LEIA-ME.md)

## Getting started

Requirements: Windows, Python 3.10+ and two packages:

```
pip install pystray pillow
```

Double-click `Token Economy.vbs`. An icon appears in the Windows tray:

- **Hover:** Codex limits (5-hour and weekly windows), today's new tokens, split between agents and RTK savings.
- **Click:** opens the dashboard in its own window.
- **Right-click:** the same summary, plus "Refresh now", "Start with Windows" and "Quit".
- **Icon color:** follows the Codex limit: green below 50%, yellow from 50%, orange from 70%, red from 90%, gray with no data.

Windows 11 hides new tray icons behind the `^` arrow. To keep it visible, drag it to the taskbar or turn it on in Settings > Personalization > Taskbar > Other system tray icons.

To use only the browser, run `python server.py` (or `iniciar.bat`) and open http://127.0.0.1:8765.

Pick the language at the top of the dashboard. The tray app follows the same choice; on first run it uses the Windows language.

## What it reads

Everything is read locally and read-only. Nothing leaves your machine.

| Tool | File | What it tells you |
|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | tokens per call, model, project, tools used |
| Claude plan limits | Anthropic's official usage endpoint (`api.anthropic.com/api/oauth/usage`), using the login Claude Code keeps in `~/.claude/.credentials.json` | 5-hour, weekly and per-model weekly windows (whatever your plan has), plan name. The token goes only to Anthropic and is never saved or shown; turn it off in Settings |
| Codex | `~/.codex/sessions/**/rollout-*.jsonl` | tokens per turn, 5-hour and weekly window %, plan |
| OpenCode | `~/.local/share/opencode/opencode.db` | tokens and cost per response, including Ollama models |
| Ollama | `%LOCALAPPDATA%/Ollama/server*.log` | requests and generation time (Ollama doesn't log tokens) |
| RTK | `%LOCALAPPDATA%/rtk/history.db` | tokens saved per command; the panel works out which agent ran each one |
| Headroom | `~/.headroom/savings_events.jsonl` | tokens compressed by the proxy, per client and model |
| Graphify | `<project>/graphify-out/graph.json` | where a graph exists and how often agents used it |

Tools you don't have are simply shown as not found.

## Token-saving tools

Token Economy detects the token-saving tools installed on your machine and shows **only those**. It looks at programs on PATH, hooks and MCP servers registered in Claude Code, Codex, OpenCode and Gemini CLI, installed skills and plugins, and each tool's data folder. It reads names and commands only, never secrets.

Tools that store their savings show tokens and US$ (minimum and estimated with cache re-reads, the same math for all of them). Tools that don't store savings say so, and show what can be known: which projects each one is set up in (its project files or a project-level MCP entry) and how often your agents queried it in each project (MCP or skill calls and runs of its program in the terminal). The panel never makes up a number.

| Tool | Kind | Savings measured | Read from |
|---|---|---|---|
| [RTK](https://github.com/rtk-ai/rtk) | command output | yes | `history.db` |
| [Headroom](https://github.com/headroomlabs-ai/headroom) | API proxy | yes | `~/.headroom/savings_events.jsonl` |
| [token-saver](https://github.com/ppgranger/token-saver) | command output | yes | `savings.db` |
| [squeez](https://github.com/claudioemmanuel/squeez) | command output | yes | `<agent>/squeez/sessions/*.jsonl` |
| [Context Mode](https://github.com/mksglu/context-mode) | command output | yes | `~/.context-mode/projects/*/context.db` |
| [lean-ctx](https://github.com/yvgude/lean-ctx) | command output | yes | `stats.json` |
| [Token Optimizer](https://github.com/alexgreensh/token-optimizer) | command output | yes | `trends.db` |
| [Caveman](https://github.com/JuliusBrussee/caveman) | response style | yes, in proxy mode | `~/.caveman/caveman.db` |
| [Kompact](https://github.com/npow/kompact) | API proxy | yes, while the proxy runs | `http://127.0.0.1:7878/api/metrics` |
| [Code Context Engine](https://github.com/elara-labs/code-context-engine) | code index | yes | `~/.cce/projects/*/memory.db` |
| [jCodeMunch](https://github.com/jgravelle/jcodemunch-mcp) | code index | yes | `~/.code-index/_savings.json` |
| [Graphify](https://github.com/safishamsi/graphify) | code index | no (usage only) | — |
| [Serena](https://github.com/oraios/serena) | code index | no (usage only) | — |
| [CodeGraph](https://github.com/colbymchenry/codegraph) | code index | no (usage only) | — |
| [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) | code index | no (usage only) | — |
| [Claude Context](https://github.com/zilliztech/claude-context) | code index | no (usage only) | — |
| [Token Reducer](https://github.com/Madhan230205/token-reducer) | code index | no | — |
| [claude-mem](https://github.com/thedotmack/claude-mem) | memory | no (usage only) | — |
| [TokenEconomizer](https://github.com/microsoft/TokenEconomizer) | memory | no | — |

Every entry was checked against the tool's own source code. The list lives in `ferramentas_economia.json`; to add a tool, add an entry (and a reader in `economia.py` if it stores its savings) and open a pull request.

## Tabs

- **Summary**: the one-glance view. Optimization score, what your usage is worth versus what you pay, current limits, usage by agent and over time, and the top insights (from the AI analysis and the automatic rules).
- **Usage, Plan limits, Agents & models, Savings, Projects & sessions, Tools**: the detail behind each number.
- **What to optimize**: how the score is built, the AI analysis and the automatic rules.
- **Settings & sources**: your subscriptions, the price tables and where each number comes from.

## Optimization score

The score (0–100) is computed by code from criteria you can change: average context size, share of calls in very long sessions, cache use, share of tokens on top-tier models, how many commands RTK could compress actually went through it, share of tool calls that only wait, and how often Codex 5-hour windows hit 95%. Each criterion has a weight, a target that earns full points and a value where it earns zero; in between it is proportional. Criteria without data are left out and the weights rescale. "What to optimize" shows your value, the target, the points and what to do for each one. Weights and targets live in `nota.py`.

## Subscriptions

In Settings, add each subscription with its monthly price (US$) and agent. The panel prorates it to the selected period (7 days of a US$ 100/month plan ≈ US$ 23) and compares it with what the same usage would cost on the API.

## Tokens or dollars

The **Tokens / US$** switch at the top shows every chart in tokens or in what the same usage would cost on the pay-per-token API. Even on a subscription, this tells you the value you are using and how much each tool saves.

Prices come from public tables the panel downloads and refreshes every week: [LiteLLM](https://github.com/BerriAI/litellm) (thousands of models from every provider), then the [OpenRouter](https://openrouter.ai) catalog. Your own values in `precos.json` win; `precos_padrao.json` is the offline fallback. The Sources tab lists the price and source used for each model, and has an "Update prices" button.

RTK savings in dollars come in two numbers. The **minimum** counts the saved output once, at the input price of the agent's model. The **estimate** (shown by default) also counts the cache re-reads: without RTK the output would stay in the conversation and be re-read on later calls, until compaction or the end of the session removes it. How long it stays is estimated per session from how fast the context grows.

## AI analysis

Under "What to optimize", pick an AI and click **Analyze with AI**. It reads a summary of your numbers (never your conversations), compares with the previous period and with the last analysis, and returns a score, a summary and concrete recommendations. Below it, the automatic rules keep running every minute at no cost.

Ways to connect an AI:

- **An installed CLI**, using the subscription you already pay for. The catalog in `provedores_ia.json` covers Claude Code, Codex, Gemini CLI, Qwen Code, Grok CLI, Cursor Agent, GitHub Copilot CLI, OpenCode, Factory Droid, Amp, Kimi and Ollama; the panel shows the ones on your PATH. Entries marked `"verificado": false` follow each tool's docs but weren't tested; add or fix entries there.
- **Any OpenAI-compatible API**: OpenAI, xAI (Grok), OpenRouter, Google Gemini, Groq, DeepSeek, Mistral, Ollama or LM Studio. The key is stored only in `.cache/config.json` on your machine; you can also type `$ENV_VAR_NAME` to read it from an environment variable.
- **A custom command**: any program that reads the prompt from standard input, or from the file passed as `{arquivo}`, and prints the JSON answer.

The prompt lives in `prompts/analise.md`; edit it to change what the AI looks at. "See what is sent" shows the exact text. Each analysis uses a few thousand tokens.

## Files

- `tray.py`: the tray app. It starts the server and the data collection inside itself.
- `server.py`: local server; collects in the background every minute and serves the page. Only the panel page can change things (requests need a header other websites can't send).
- `sinais.py`, `economia.py`, `ferramentas_economia.json`: detection of token-saving tools and the readers of their savings.
- `collector.py`: reads every source and builds the numbers. Run `python collector.py` to test it alone.
- `precos.py`, `precos.json`, `precos_padrao.json`: prices (see above).
- `ia.py`, `provedores_ia.json`, `prompts/analise.md`: the AI analysis.
- `static/`: the page. Translations live in `static/i18n.js`; to add a language, copy the `en` block. Charts use Chart.js from cdnjs, so they need internet.
- `.cache/`: how far each log has been read, downloaded price tables, settings, past analyses and the tray log. Safe to delete; the next run rebuilds it.

## Limitations

- Claude Code doesn't write its plan-limit percentage to its logs. The panel shows it when Headroom has a recent reading; otherwise use `/usage` in Claude Code.
- RTK token counts are estimates (bytes ÷ 4). Outputs above 7,500 tokens are left out, the same as `rtk gain`.
- The agent behind each RTK command is inferred by matching it against the commands each agent ran; about 5% stays unidentified.
