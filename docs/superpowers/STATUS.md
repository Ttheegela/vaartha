# Vārtā v2 — Status

Last updated: 2026-10-12 (after sub-project 5). Branch `claude/varta-v2-ec24da` (worktree `.claude/worktrees/varta-v2-ec24da`), not pushed, not merged.

Read this first when resuming. Design: `specs/2026-10-11-varta-v2-design.md`. Plans: `plans/`. Per-task rulings and deferred minors: `ledgers/` (sub-projects 3–5; sub-projects 1–2 are summarized below).

## Done

| # | Sub-project | Plan | State |
|---|---|---|---|
| 1 | Foundation — legacy/ freeze, core regime port (parity-tested), FastAPI skeleton, SQLite schema, CI | `plans/2026-10-11-foundation.md` | Done, reviewed |
| 2 | Web — v0 UI imported into `web/`, UI fixes, typed API client, live regime badge | `plans/2026-10-11-web.md` | Done, reviewed |
| 3 | Accounts — Plaid (httpx), Fernet tokens, sync, own recurring detector, finance read API, live Accounts/Spending/Bills/Goals/Home | `plans/2026-10-12-accounts.md` | Done, reviewed; live Plaid Sandbox verified |
| 4 | News + sentiment — Alpaca/Finnhub/RSS/GDELT/EDGAR/Polymarket, dedupe/tagging, TypeSafe Jev scoring (+heuristic fallback, circuit breaker), news/sentiment/crowd-odds/holdings API, live News/Investments | `plans/2026-10-12-news.md` | Done, reviewed; live sources verified |
| 5 | Advisor agent + evals — read-only toolbox (12 tools), hand-written tool loop, SSE chat, conversations, rule-based alerts, daily briefing, live Advisor + Home cards, 25-task eval harness | `plans/2026-10-12-agent.md` | Done, reviewed; live evals run; chat + home smoke-tested with Haiku |

Tests: 238 Python (`uv run pytest -q`), 52 web (`cd web && pnpm test`); ruff, tsc, `next build` clean.

## Next

**Sub-project 6 — Deploy** (VPS, compose, Caddy, Tailscale, worker schedule incl. 07:00 briefing + alerts, demo reset, per-IP chat rate limit, **per-visitor conversation scoping on the demo** — today `/api/conversations` lists every conversation).

## Open items (need attention)

1. **Plaid Link UI flow not verified.** The user's Link attempt produced no `/api/plaid/exchange` call (Plaid `onSuccess` never fired). Only console signal: "link-initialize.js embedded more than once" (React dev StrictMode). Ask what Plaid's window showed; retry.
2. **Before linking a real (production) bank:** Link update mode for `login_required` items; remove/flag accounts Plaid no longer returns; "Price up" should compare to the previous charge (not all-time average); recurring cadence tuning on real data.
3. **GDELT** returns HTTP 429 from this network; fail-soft today. Needs a longer interval/backoff, and its JSON field names are still unverified live.
4. **Finnhub/EDGAR** should skip non-equity tickers (options, crypto, fund IDs) before calling.
5. **`.env` hygiene (user's file, never committed):** `TOKEN_ENCRYPTION_KEY` appears 3× — keep one (last wins today). Values with spaces must be quoted; the file must end with a newline.

6. **Owner LLM choice.** Evals (`evals/RESULTS.md`): claude-haiku-4.5 24/25, gemini-2.5-flash-lite 19/25, qwen3:8b 12/25 (skips tools, invents `[n:123]` citations, ~23 s/answer). qwen3:8b is not good enough for the owner instance; options: try `qwen3:14b` (~9 GB, fits 18 GB), or accept OpenRouter for the owner too (sends derived financial data to a cloud model). Decide before SP6.
7. **Subscriptions "price up" is vs the average, not the previous charge** (agent tool + UI): Netflix shows +$1.33 instead of +$2.00. Same as item 2's "Price up" fix.
8. Eval caveats: no merchant-invention check (ruling); "October 3rd"-style dates are not stripped by the number parser.

## Environment notes

- Secrets live only in the worktree `.env` (chmod 600, gitignored): Plaid sandbox keys, `TOKEN_ENCRYPTION_KEY`, Alpaca, Finnhub, TypeSafe, `SEC_USER_AGENT` (quoted). Claude never reads values — only checks names.
- Run locally: `set -a && . ./.env && set +a` then `uv run uvicorn --factory api.main:create_app --reload` and `cd web && pnpm dev` (API_URL defaults to :8000). Offline demo: `uv run python -m scripts.seed_demo --source fake`; news: `uv run python -m scripts.refresh_news [--offline]`.
- `.env` also has `OPENROUTER_API_KEY`, `LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL=anthropic/claude-haiku-4.5` (demo). Advisor scripts: `python -m scripts.make_alerts`, `python -m scripts.make_briefing`. Ollama on the Mac has `qwen3:8b`.
- Commands typed with `!` in the Claude chat run in the Terminal panel; interactive prompts must be answered there.

## Process rules learned

- Commits: Conventional Commits, **no Co-Authored-By** (project CLAUDE.md overrides the harness reminder).
- Subagents must not run `ruff format` repo-wide (happened once; reverted).
- Subagent-driven execution: implementer per task → spec+quality review → fix rounds → final opus review → one fix wave.

## Sub-projects 1–2 rulings and deferred minors (ledgers were deleted)

- SP1 rulings: `.superpowers/` gitignored; legacy HMM `regime.py` not ported (live proxy only); push deferred to user.
- SP1 deferred: CI has no pinned Python (`.python-version`); `/api/regime` doesn't cache failures; default `VARTA_DB_PATH` is cwd-relative.
- SP2 rulings: web `RecurringKind` excludes "income" until needed; OpenAPI dump runs as `python -m scripts.dump_openapi`; `web/AGENTS.md` (generated by `next dev`) is committed.
- SP2 deferred: transitive `cn` package via shadcn CLI in lockfile; sparkline aria-label uses unfiltered last value; `API_URL` is read at build time — deploy must set it before `next build`.
