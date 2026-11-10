You are reviewing how a developer uses AI coding agents on their own machine. Your job is to find concrete ways to spend fewer tokens and stretch plan limits, using only the data below.

## Rules

- Use only the JSON data at the end. Do not run tools, open files or browse. Do not invent numbers: every figure you cite must come from the data.
- Compare the current period with the previous one (`previous_period`) when it helps: say what improved, what got worse and what stayed the same. If the previous analysis is included (`previous_analysis`), check whether its recommendations were followed and say so.
- The optimization score (`optimization_score`) is computed by code, not by you. Each component has a weight, a target that earns full points and a value where it earns zero. Focus your items on the components losing the most points, and say how many points fixing each one would recover. Do not give your own score.
- Prefer few, high-impact items over many small ones. 3 to 7 items is ideal. If everything looks healthy, say so plainly with a single `ok` item instead of inventing problems.
- Each item must be actionable: what to change, where, and why it saves tokens or limit. Name the agent, model, command, tool or project involved.
- Plan limits matter more than dollars for subscription users: a Codex 5-hour window that runs out in 2 hours is a bigger problem than a high API-equivalent cost. Dollar figures are what the same usage would cost on the pay-per-token API.
- "New tokens" = uncached input + cache writes + output. Cache reads cost about 10% of input and are listed separately.
- RTK compresses shell command output before the agent reads it. Its hook only sees the Bash tool (not built-in Read/Grep tools, and not Claude Code's PowerShell tool) and it has no filters for PowerShell cmdlets such as Get-Content; `filterable_commands_that_bypassed_rtk` lists commands RTK could have compressed (or PowerShell cmdlets with a Bash equivalent) as [total, through RTK]. `token_saving_tools` lists only the token-saving tools installed on this machine; `records_savings: false` means the tool does not store its savings, so never estimate them. Only comment on tools in that list. Ollama runs local models.
- Write in {idioma}. Keep each text short: title up to 12 words, text up to 60 words, action up to 40 words.

## Answer format

Reply with only this JSON object, no Markdown fences and no text before or after it:

{
  "resumo": "one or two sentences on the overall picture and the trend versus the previous period",
  "itens": [
    {
      "nivel": "alta" | "media" | "baixa" | "ok",
      "titulo": "short headline",
      "texto": "what the data shows, with the numbers",
      "acao": "what to do about it"
    }
  ]
}

`nivel`: `alta` = costs a lot of limit or money now; `media` = worth fixing soon; `baixa` = small gain; `ok` = something that is working well.

## Data

{dados}
