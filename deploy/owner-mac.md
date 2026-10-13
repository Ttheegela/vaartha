# Owner instance on the Mac

Real accounts (Plaid), Ollama or OpenRouter LLM, reachable from your phone only over Tailscale.

## 1. Env file

```
mkdir -p ~/.config/vaartha && chmod 700 ~/.config/vaartha
$EDITOR ~/.config/vaartha/owner.env      # see deploy/owner.env.example
chmod 600 ~/.config/vaartha/owner.env
```

Set: `PLAID_ENV=production` with `PLAID_CLIENT_ID` / `PLAID_SECRET` (Trial keys) and a new
`TOKEN_ENCRYPTION_KEY` (`uv run python -m scripts.new_token_key`); the news keys
(`FINNHUB_API_KEY`, `TYPESAFE_API_KEY`, `SEC_USER_AGENT`); `OPENROUTER_API_KEY` (owner key with its
own cap), `LLM_BASE_URL`, `LLM_MODEL`; `VARTA_TZ`. Do not set `VARTA_INSTANCE=demo`. The script
forces the instance, DB and backup paths, and the worker.

## 2. Run

```
scripts/owner.sh check
scripts/owner.sh start      # first start builds the web (needs pnpm, node, uv)
open http://127.0.0.1:3000
scripts/owner.sh status | stop
```

Logs: `~/Library/Logs/Vaartha`.

## 3. Phone access (Tailscale)

Install Tailscale on the Mac and phone, then `tailscale serve --bg 3000` and open
`https://<mac>.<tailnet>.ts.net` on the phone. Works only while the Mac is awake.
Never use `tailscale funnel`: it is public.

## 4. Start at login

```
cp deploy/macos/dev.vaartha.owner.plist.template ~/Library/LaunchAgents/dev.vaartha.owner.plist
# edit it: replace <repo> and <user>
mkdir -p ~/Library/Logs/Vaartha
launchctl load ~/Library/LaunchAgents/dev.vaartha.owner.plist
```

## Notes

- Scheduled jobs catch up on wake.
- Backups: `~/Library/Application Support/Vaartha/backups`.
- Moving to a VPS later: restore the backup and follow `docs/superpowers/plans/2026-10-12-deploy.md`.
