# Contributing to Token Economy

Thanks for helping! Bug reports, new token-saving tools, new agents, translations and fixes are all welcome.

## Good first contributions

- **Add a token-saving tool.** Add an entry to `savings_tools.json` with its detection signals (programs, hooks, MCP servers, skills, plugins, data folders, project files). If the tool stores how much it saves, add a reader in `savings.py`. Check every path and format against the tool's own source code, not its README.
- **Add or fix a translation.** All UI text lives in `static/i18n.js`. To add a language, copy the `en` block and translate the values.
- **Add an AI provider for the analysis.** Edit `ai_providers.json`. Mark entries you could not test with `"verified": false`.
- **Report a wrong number.** Open an issue with the tab, the number you expected and why (for example the output of `rtk gain` or `/usage`). Never paste your API keys, logs with private code, or `.cache/` files.

## Development

```
pip install pystray pillow
python server.py --no-browser      # dashboard at http://127.0.0.1:8765
python collector.py                # run the data collection alone
python server.py --demo            # fake data, for screenshots and UI work
```

No build step and no third-party Python packages besides the tray icon. Keep it that way when you can: the app reads local files with the standard library.

Rules of thumb:

- **Read-only.** The app must never write to the files of the agents or tools it reads.
- **Never invent a number.** If a tool does not record its savings, show usage only and say so.
- **No secrets leave the machine.** Detection reads names and commands, never tokens or keys. The only outgoing calls are the public price tables, the official usage endpoints of the user's own accounts, the update check on GitHub, and the AI analysis the user starts.
- **Code, comments and commits in English.** UI text goes through `static/i18n.js`.

## Pull requests

1. Fork, create a branch, make your change.
2. Test it with your real data and with `--demo`.
3. Open the pull request describing what changed and how you checked it.

## Contributor License Agreement

Token Economy is released under the AGPL-3.0 and is also offered under a separate commercial license (see [Commercial use](README.md#license-and-commercial-use)). To keep that possible, every contribution needs the agreement below. By opening a pull request you confirm you agree to it.

> **Token Economy Contributor License Agreement**
>
> 1. You are the author of your contribution, or have the right to submit it, and it does not include code you are not allowed to share.
> 2. You keep the copyright of your contribution.
> 3. You grant the Token Economy maintainer (GitHub user `Baeta78`) and their successors a perpetual, worldwide, non-exclusive, royalty-free, irrevocable license to use, copy, modify, distribute and sublicense your contribution, under the AGPL-3.0 and under any other license, including commercial licenses.
> 4. Your contribution is also published under the AGPL-3.0, so it always stays available to everyone as free software.
> 5. Your contribution is provided "as is", without warranties.

If you can't agree to this (for example because of your employer), say so in the pull request before we merge it.
