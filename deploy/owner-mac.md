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
own cap), `LLM_BASE_URL`, `LLM_MODEL`; `VARTA_TZ`; `OWNER_NAME` (your first name for the home greeting). Do not set `VARTA_INSTANCE=demo`. The script
forces the instance, DB and backup paths, and the worker.

Values containing spaces must be quoted, e.g. `SEC_USER_AGENT="Your Name you@example.com"`; the file is
sourced as shell and `check` rejects it otherwise.

## 2. Run

```
scripts/owner.sh check
scripts/owner.sh start      # first start builds the web (needs pnpm, node, uv)
open http://127.0.0.1:3100
scripts/owner.sh status | stop
```

`start` rebuilds the web when the git commit changed since the last build (after a pull; about a minute). The stamp only tracks commits: after a manual `pnpm build` or uncommitted web changes, run `rm web/.next/owner-build-stamp` to force an owner rebuild.
Logs: `~/Library/Logs/Vaartha`.

## 3. Phone access (Tailscale)

Install Tailscale on the Mac and phone, then `tailscale serve --bg 3100` and open
`https://<mac>.<tailnet>.ts.net` on the phone. Works only while the Mac is awake.
Never use `tailscale funnel`: it is public.

OAuth banks (Chase, PNC and others) return to `https://<mac>.<tailnet>.ts.net/oauth-return`. Add that exact
URL in the Plaid Dashboard (Developers > API > Allowed redirect URIs, production) and set
`PLAID_REDIRECT_URI` to the same value in `owner.env`, then restart. Without it, OAuth banks fail or are hidden in Link.

## 4. Start at login

macOS blocks background jobs from reading `~/Desktop`, `~/Documents` and `~/Downloads`
("Operation not permitted"), so the login agent runs a **runtime copy** outside those folders
instead of granting a shell Full Disk Access:

```
git clone --branch <branch> https://github.com/Ttheegela/vaartha.git ~/Developer/vaartha
cd ~/Developer/vaartha && uv sync --locked && (cd web && pnpm install --frozen-lockfile)
sed -e "s#<repo>#$HOME/Developer/vaartha#" -e "s#<user>#$(whoami)#g" \
  deploy/macos/dev.vaartha.owner.plist.template | grep -v 'Replace <repo>' \
  > ~/Library/LaunchAgents/dev.vaartha.owner.plist
plutil -lint ~/Library/LaunchAgents/dev.vaartha.owner.plist
mkdir -p ~/Library/Logs/Vaartha
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.vaartha.owner.plist
```

The agent runs `owner.sh start` once at login and exits; the API and web keep running
(`AbandonProcessGroup`). Logs: `~/Library/Logs/Vaartha/launchd.log`. The data dir and env file
are the same as a manual start, so both share one database.

- Update the runtime copy: `cd ~/Developer/vaartha && git pull && uv sync --locked && (cd web && pnpm install --frozen-lockfile) && scripts/owner.sh stop && scripts/owner.sh start` (the web rebuilds when the commit changes).
- Disable: `launchctl bootout gui/$(id -u)/dev.vaartha.owner && rm ~/Library/LaunchAgents/dev.vaartha.owner.plist`.
- Run only one copy at a time (manual `owner.sh` from another checkout uses the same ports and pidfiles).

## Notes

- Scheduled jobs catch up on wake.
- Backups: `~/Library/Application Support/Vaartha/backups`.
- Moving to a VPS later: restore the backup and follow `docs/superpowers/plans/2026-10-12-deploy.md`.

## Stop using Vārtā

1. `scripts/owner.sh stop`.
2. Run `scripts/remove_item.py` for each item (`--list` shows them; it revokes access at Plaid and deletes the item's local data).
3. Delete `~/Library/Application Support/Vaartha` and `~/.config/vaartha`.

Net-worth snapshots keep aggregate history until the data dir is deleted.
