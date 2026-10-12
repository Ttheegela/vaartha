# CLAUDE.md — Vārtā v2

Read before changing anything. Design spec: `docs/superpowers/specs/2026-10-11-varta-v2-design.md`.
Plans: `docs/superpowers/plans/`.

## What this is
Personal finance + investing advisor agent (Origin-style). Two instances from one codebase:
- owner: Tarun's real accounts (Plaid Trial), Tailscale-only, LLM = Ollama on his Mac
- demo: public, Plaid Sandbox, LLM = OpenRouter, rate-limited

## Layout
- `core/` pure Python analytics (Polars, no web deps, no I/O at import)
- `api/` FastAPI app (`uvicorn --factory api.main:create_app`), SQLite via stdlib sqlite3 (WAL)
- `web/` Next.js (from v0). Pure UI logic in `web/lib/*.ts` with relative `.ts` imports, tested by `pnpm test` (node:test). Typed client from `web/openapi.json` (`pnpm gen:api`).
- `worker/` scheduled jobs (later), `evals/` (later), `deploy/` (later)
- `legacy/` v1 Streamlit app — frozen, reference only, never edit

## Rules
- Polars only. pandas allowed only in `core/prices.py` and tests that fake yfinance.
- Docstring on every public function and module. No magic numbers: name constants at module top.
- No network or disk side effects at import time.
- Tests: pytest, no live network (fake/replay external APIs). `uv run pytest && uv run ruff check .` must pass before commit.
- The agent's tools are read-only. Never pass Plaid tokens or account numbers to any LLM.
- Never read, print or log secrets. Never commit `.env`, `*.db`, runtime `data/`.
- Commits: Conventional Commits, no `Co-Authored-By` line. Never force-push.
- Verify library APIs against installed versions or docs before using them.
- When data is missing or unverified, say so; never invent numbers.
