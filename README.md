# Vārtā

A personal finance and investing advisor with an AI agent: linked accounts (Plaid), a bills and
subscriptions calendar, budgets and goals, and investing advice informed by live news, crowd
sentiment and a market-regime engine. Not financial advice.

Design: [`docs/superpowers/specs/2026-10-11-varta-v2-design.md`](docs/superpowers/specs/2026-10-11-varta-v2-design.md)
v1 (course project, Streamlit) is frozen in [`legacy/`](legacy/).

## Develop

```bash
uv sync && uv run pytest  # API + core
cp .env.example .env && uv run python -m scripts.new_token_key >> .env
set -a && . ./.env && set +a && uv run python -m scripts.seed_demo --source fake  # offline demo data
uv run uvicorn --factory api.main:create_app --reload  # API on :8000
cd web && pnpm install && pnpm dev  # UI on :3000, /api proxied to :8000
```

With Plaid Sandbox keys in `.env`: `uv run python -m scripts.seed_demo --source sandbox`, or use **Link account** in the UI.

After changing an API route: `uv run python -m scripts.dump_openapi && (cd web && pnpm gen:api)`.
