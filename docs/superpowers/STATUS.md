# Vārtā v2 — Status

Last updated: 2026-10-13 (after Heroku demo + Mac owner plan). Branch `claude/varta-v2-ec24da` (worktree `.claude/worktrees/varta-v2-ec24da`), not pushed, not merged.

Read this first when resuming. Design: `specs/2026-10-11-varta-v2-design.md`. Plans: `plans/`. Per-task rulings and deferred minors: `ledgers/` (sub-projects 3–6; sub-projects 1–2 are summarized below).

## Done

| # | Sub-project | Plan | State |
|---|---|---|---|
| 1 | Foundation — legacy/ freeze, core regime port (parity-tested), FastAPI skeleton, SQLite schema, CI | `plans/2026-10-11-foundation.md` | Done, reviewed |
| 2 | Web — v0 UI imported into `web/`, UI fixes, typed API client, live regime badge | `plans/2026-10-11-web.md` | Done, reviewed |
| 3 | Accounts — Plaid (httpx), Fernet tokens, sync, own recurring detector, finance read API, live Accounts/Spending/Bills/Goals/Home | `plans/2026-10-12-accounts.md` | Done, reviewed; live Plaid Sandbox verified |
| 4 | News + sentiment — Alpaca/Finnhub/RSS/GDELT/EDGAR/Polymarket, dedupe/tagging, TypeSafe Jev scoring (+heuristic fallback, circuit breaker), news/sentiment/crowd-odds/holdings API, live News/Investments | `plans/2026-10-12-news.md` | Done, reviewed; live sources verified |
| 5 | Advisor agent + evals — read-only toolbox (12 tools), hand-written tool loop, SSE chat, conversations, rule-based alerts, daily briefing, live Advisor + Home cards, 25-task eval harness | `plans/2026-10-12-agent.md` | Done, reviewed; live evals run; chat + home smoke-tested with Haiku |
| 6 | Deploy (code) — per-visitor conversations (demo), chat + admin rate limits, local-tz today, JSON logs, scheduled worker (sync/news/alerts/briefing/backup/demo reset), Docker images, Compose demo/owner profiles on separate networks, Caddy (public demo, Tailscale-only owner), CI image builds, runbook `deploy/README.md` | `plans/2026-10-12-deploy.md` | Code done, reviewed; **not provisioned yet** (superseded for hosting by row 7; the VPS path stays as an alternative) |
| 7 | Hosting — demo on Heroku (GitHub Student credit, `deploy/heroku.md`), owner on the Mac via `scripts/owner.sh` + `tailscale serve` (`deploy/owner-mac.md`) | `plans/2026-10-13-heroku-mac.md` | Code done, reviewed; **not provisioned** |

Tests: 290 Python (`uv run pytest -q`), 55 web (`cd web && pnpm test`); ruff, tsc, `next build` clean.

## Live

- **Demo:** https://demo.vaartha.tech (web, Heroku `vaartha-web`, Eco) + https://api.vaartha.tech (API, Heroku `vaartha-api`, Basic, embedded scheduler). Deployed 2026-10-13 via `gh workflow run deploy-heroku.yml --ref claude/varta-v2-ec24da`. Verified: HTTPS (ACM), /healthz, Plaid Sandbox seed, news + Jev scoring, briefing on Home, SSE chat with CORS + `.vaartha.tech` cookie, 21st chat/hour → 429. HTTP → HTTPS 308 redirects on both hosts (2026-10-13).
- Plaid trial commitments: secret scanning + push protection + Dependabot security updates on (0 alerts), weekly Dependabot version PRs, `scripts/remove_item.py` unlinks a bank and deletes its data, FileVault on for the owner DB. MFA + password manager are Tarun's to keep.
- Heroku credit: GitHub Student $312, expires 2028-09-30. Domain vaartha.tech (Namecheap) expires 2027-10-13. Calendar reminders exist for both.

## Next

0. **Owner instance is live on the Mac (2026-10-14):** `scripts/owner.sh start`, web :3100, tailnet https://taruns-macbook-pro.tail9ec172.ts.net (tailscale serve, tailnet-only). Starts at login via launch agent `dev.vaartha.owner` running the runtime copy at `~/Developer/vaartha` (macOS blocks background access to ~/Desktop); update it with `git pull` there (see deploy/owner-mac.md §4). Plaid production: 5 of 10 Trial connections used (Amex, Bilt, Capital One, Chase via OAuth redirect, Robinhood). Plaid company profile + data-security questionnaire still recommended (removes the "building something new" screen).

1. **Owner instance on the Mac:** create `~/.config/vaartha/owner.env` (mode 600) from `deploy/owner.env.example`, then `scripts/owner.sh check` / `start`, link a real bank (open items 1–2), phone via `tailscale serve`. `start`/`stop`/launchd are not yet verified live.
2. Merge v2 into `main` when ready (only the deploy workflow is on `main` today).
3. Watch the demo: cash flow/bills fill in after Plaid Sandbox delivers transactions (6-hourly sync); `heroku logs -t -a vaartha-api` for R14 memory warnings.
4. **Passkey lock + Dock app (2026-10-14):** owner instance gated by a passkey (`PASSKEY_RP_ID`/`PASSKEY_ORIGIN` required in `owner.env`; `git pull` in `~/Developer/vaartha` and set them before the next start); setup/recovery in `deploy/owner-mac.md` §5–6.

## Open items (need attention)

1. **Plaid Link UI flow: fix in, browser click-through pending.** Likely cause of the missing `onSuccess` was react-plaid-link re-inserting link-initialize.js under StrictMode ("embedded more than once"); the web now loads the script once before mounting Link (2026-10-14). Backend verified against Sandbox; see `PLAID_PLAN.md` (build-kit plan, human tasks, rules checked).
2. **Before linking a real (production) bank:** `PLAID_PLAN.md` human tasks H1–H4 (Production secret, redirect URI `https://<mac>.<tailnet>.ts.net/oauth-return` + `PLAID_REDIRECT_URI`, company profile/security questionnaire, DTM); remove/flag accounts Plaid no longer returns; "Price up" should compare to the previous charge (not all-time average); recurring cadence tuning on real data.
3. **GDELT** returns HTTP 429 from this network; fail-soft today. Needs a longer interval/backoff, and its JSON field names are still unverified live.
4. **Finnhub/EDGAR** should skip non-equity tickers (options, crypto, fund IDs) before calling.
5. **`.env` hygiene (user's file, never committed):** `TOKEN_ENCRYPTION_KEY` appears 3× — keep one (last wins today). Values with spaces must be quoted; the file must end with a newline.

6. **Owner LLM: decided — OpenRouter (Haiku) for both instances** (spec §4 decision note). Local Ollama models removed from the Mac. SP6 needs no Tailscale link from the VPS to the Mac for the LLM.
7. **Subscriptions "price up" is vs the average, not the previous charge** (agent tool + UI): Netflix shows +$1.33 instead of +$2.00. Same as item 2's "Price up" fix.
8. Eval caveats: no merchant-invention check (ruling); "October 3rd"-style dates are not stripped by the number parser.

9. **Deploy follow-ups:** runbook restore/key-generation steps verified only by read-through until the first VPS run; Plaid Production OAuth banks may need an HTTPS redirect URI on the owner instance; backups live on the same volume (off-box copy is manual).
10. **Calendar reminders set for hosting renewals:** domain transfer (2027-08-16) and Heroku student credit end (2028-08-15).

## Environment notes

- Secrets live only in the worktree `.env` (chmod 600, gitignored): Plaid sandbox keys, `TOKEN_ENCRYPTION_KEY`, Alpaca, Finnhub, TypeSafe, `SEC_USER_AGENT` (quoted). Claude never reads values — only checks names.
- Run locally: `set -a && . ./.env && set +a` then `uv run uvicorn --factory api.main:create_app --reload` and `cd web && pnpm dev` (API_URL defaults to :8000). Offline demo: `uv run python -m scripts.seed_demo --source fake`; news: `uv run python -m scripts.refresh_news [--offline]`.
- `.env` also has `OPENROUTER_API_KEY`, `LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL=anthropic/claude-haiku-4.5` (demo). Advisor scripts: `python -m scripts.make_alerts`, `python -m scripts.make_briefing`. No local Ollama models (dropped).
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
