# Heroku demo deploy

Two container apps (API + web) on Heroku, released by the `deploy-heroku` GitHub workflow.
Placeholders: `<domain>` (e.g. vaartha.dev), `<api-app>`, `<web-app>`.

**A shared custom domain is REQUIRED.** Use `demo.<domain>` (web) and `api.<domain>` (API) with
`COOKIE_DOMAIN=.<domain>`. Two `*.herokuapp.com` hosts are cross-site (herokuapp.com is on the
Public Suffix List), so the visitor cookie (SameSite=Lax) and credentialed browser calls will not work there.

1. Redeem the GitHub Student offer (card required, $13 a month for 24 months). Install the Heroku CLI, `heroku login`.
2. Create apps:
   `heroku create <api-app> --stack container` and `heroku create <web-app> --stack container`.
3. API config vars, set from your terminal (never paste values into chat or commit them):
   - `VARTA_INSTANCE=demo`, `PLAID_ENV=sandbox`, `PLAID_CLIENT_ID`, `PLAID_SECRET`
   - `TOKEN_ENCRYPTION_KEY`: `heroku config:set "$(uv run python -m scripts.new_token_key)" -a <api-app>`
   - `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `FINNHUB_API_KEY`, `TYPESAFE_API_KEY`, `SEC_USER_AGENT`
   - `OPENROUTER_API_KEY` (demo key with a spend cap), `LLM_BASE_URL`, `LLM_MODEL`
   - `CHAT_RATE_PER_HOUR=20`, `VARTA_TZ`, `TRUST_PROXY=1`, `RUN_WORKER=1`
   - `CORS_ORIGINS=https://demo.<domain>`, `COOKIE_DOMAIN=.<domain>`, `VARTA_DB_PATH=/tmp/varta.db`
   - Optional: `VARTA_BACKUP_DIR` (not needed; the filesystem is ephemeral).
4. Web config vars: `heroku config:set API_URL=https://api.<domain> VARTA_INSTANCE=demo -a <web-app>`.
5. GitHub repo Settings, Secrets and variables:
   - Secret `HEROKU_API_KEY` (from `heroku authorizations:create`).
   - Variables `HEROKU_API_APP`, `HEROKU_WEB_APP`, `NEXT_PUBLIC_API_BASE=https://api.<domain>`.
6. Actions tab, run the "deploy-heroku" workflow. (Images are built on amd64 runners and released via the Platform API formation endpoint.)
7. Dynos: `heroku ps:type web=basic -a <api-app>`. Web app: `eco` (sleeps; total about $12 a month) or `basic` (always on; about $14 a month). Then `heroku ps:scale web=1` on both.
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
    - A Basic dyno has 512 MB. If logs show R14, set `WEB_CONCURRENCY=1` (uvicorn already runs one worker).
    - Calendar reminders: credit end and domain transfer.
