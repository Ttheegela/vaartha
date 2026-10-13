# Heroku demo deploy

Two container apps (API + web) on Heroku, released by the `deploy-heroku` GitHub workflow.
Placeholders: `<domain>` (e.g. vaartha.dev), `<api-app>`, `<web-app>`.

**A shared custom domain is REQUIRED.** Use `demo.<domain>` (web) and `api.<domain>` (API) with
`COOKIE_DOMAIN=.<domain>`. Two `*.herokuapp.com` hosts are cross-site (herokuapp.com is on the
Public Suffix List), so the visitor cookie (SameSite=Lax) and credentialed browser calls will not work there.

1. Redeem the GitHub Student offer (card required, $13 a month for 24 months). Install the Heroku CLI, `heroku login`.
2. Create apps:
   `heroku create <api-app> --stack container` and `heroku create <web-app> --stack container`.
3. API config vars, set from your terminal. `heroku config:set` prints the resulting KEY: value pairs, so
   redirect output (`> /dev/null`) on every command that carries a secret, and read secrets without echo or shell history:
   ```
   read -rs "?Plaid secret: " v && heroku config:set PLAID_SECRET="$v" -a <api-app> > /dev/null && unset v
   ```
   (zsh syntax; in bash use `read -rsp "Plaid secret: " v`.) `PLAID_SECRET="$v"` is briefly visible to local `ps`; acceptable on a personal machine. Repeat for each secret below.
   - Secrets: `PLAID_CLIENT_ID`, `PLAID_SECRET`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `FINNHUB_API_KEY`, `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY` (demo key with a spend cap)
   - `TOKEN_ENCRYPTION_KEY`: `heroku config:set "$(uv run python -m scripts.new_token_key)" -a <api-app> > /dev/null`
   - Non-secret: `VARTA_INSTANCE=demo`, `PLAID_ENV=sandbox`, `SEC_USER_AGENT`, `LLM_BASE_URL`, `LLM_MODEL`
   - `CHAT_RATE_PER_HOUR=20`, `VARTA_TZ`, `TRUST_PROXY=1`, `RUN_WORKER=1`
   - `CORS_ORIGINS=https://demo.<domain>`, `COOKIE_DOMAIN=.<domain>`, `VARTA_DB_PATH=/tmp/varta.db`
   - `VARTA_BACKUP_DIR=/tmp/backups` (the filesystem is ephemeral)
4. Web config vars: `heroku config:set API_URL=https://api.<domain> VARTA_INSTANCE=demo -a <web-app>`.
5. GitHub repo Settings, Secrets and variables:
   - Secret `HEROKU_API_KEY` (from `heroku authorizations:create`).
   - Variables `HEROKU_API_APP`, `HEROKU_WEB_APP`, `NEXT_PUBLIC_API_BASE=https://api.<domain>`.
6. Run the "deploy-heroku" workflow. It only appears in the Actions tab once it is on the default branch: merge to main first, or run `gh workflow run deploy-heroku.yml --ref claude/varta-v2-ec24da`. (Images are built on amd64 runners and released via the Platform API formation endpoint.)
7. Dynos:
   - `heroku ps:type web=basic -a <api-app>`
   - `heroku ps:type web=eco -a <web-app>` (sleeps) or `web=basic` (always on)
   Basic (api) + Eco (web) is $12 a month and fits the $13 credit. Basic + Basic is $14, about $1 a month on the card.
   Then scale both:
   - `heroku ps:scale web=1 -a <api-app>`
   - `heroku ps:scale web=1 -a <web-app>`
8. Domains:
   - `heroku domains:add api.<domain> -a <api-app>` and `heroku domains:add demo.<domain> -a <web-app>`.
   - At Name.com add two CNAME records pointing at the DNS targets Heroku prints.
   - `heroku certs:auto:enable -a <app>` on both. ACM is free.
9. Verify:
   - `curl https://api.<domain>/healthz`
   - Demo pages show data within a minute or two of first boot (boot reseed).
   - The 21st chat in an hour returns 429.
   - `heroku logs -t -a <api-app>` shows JSON lines.
10. Notes:
    - Conversations reset at the daily dyno restart, and the demo data reseeds then.
    - A Basic dyno has 512 MB and the API image already runs a single uvicorn process. First check memory in `heroku logs` (R14 lines show usage). Standard-1X is also 512 MB, so it does not help. The real lever is Standard-2X (1 GB, $50 a month per heroku.com/pricing on 2026-10-13; check current pricing), well outside the $13 credit. Cheaper alternative: run the demo API on the VPS/Compose path in `deploy/README.md`. `RUN_WORKER=0` is not an option on Heroku (separate dynos have separate disks).
    - Calendar reminders: credit end and domain transfer.
