# Vārtā

A personal finance and investing advisor with an AI agent: linked accounts (Plaid), a bills and
subscriptions calendar, budgets and goals, and investing advice informed by live news, crowd
sentiment and a market-regime engine. Not financial advice.

Design: [`docs/superpowers/specs/2026-10-11-varta-v2-design.md`](docs/superpowers/specs/2026-10-11-varta-v2-design.md)
v1 (course project, Streamlit) is frozen in [`legacy/`](legacy/).

## Develop

```bash
uv sync
uv run pytest
uv run uvicorn --factory api.main:create_app --reload
```
