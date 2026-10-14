# CLAUDE.md — Vārtā v2

Read before changing anything. Design spec: `docs/superpowers/specs/2026-10-11-varta-v2-design.md`.
Plans: `docs/superpowers/plans/`. Current status, open items and next step: `docs/superpowers/STATUS.md` (read it first when resuming).

## What this is
Personal finance + investing advisor agent (Origin-style). Two instances from one codebase:
- owner: Tarun's real accounts (Plaid Trial), on Tarun's Mac (`scripts/owner.sh`, exposed only via `tailscale serve`), LLM = OpenRouter (local Ollama dropped 2026-10-12: too slow, overheats the laptop)
- demo: public, hosted on Heroku, Plaid Sandbox, LLM = OpenRouter, rate-limited

## Layout
- `core/` pure Python analytics (Polars, no web deps, no I/O at import)
- `api/` FastAPI app (`uvicorn --factory api.main:create_app`), SQLite via stdlib sqlite3 (WAL)
- `web/` Next.js (from v0). Pure UI logic in `web/lib/*.ts` with relative `.ts` imports, tested by `pnpm test` (node:test). Typed client from `web/openapi.json` (`pnpm gen:api`).
- `evals/` advisor evals: `uv run python -m evals.run --model ID --base-url URL` (live, manual), `--report` writes `evals/RESULTS.md`; CI replays `evals/recordings/`
- `worker/` scheduler loop (`python -m worker.main`); `deploy/` Compose + Caddy + runbook (`deploy/README.md`)
- Hosting: demo on Heroku (`deploy/heroku.md`), owner on the Mac (`deploy/owner-mac.md`, `scripts/owner.sh`); VPS alternative in `deploy/README.md`
- Owner lock: passkey (WebAuthn) via `PASSKEY_RP_ID`/`PASSKEY_ORIGIN`; CLI `uv run python -m scripts.passkey setup-code|reset|list`; see `deploy/owner-mac.md`
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
