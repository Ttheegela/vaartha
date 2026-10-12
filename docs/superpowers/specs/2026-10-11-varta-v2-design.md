# Vārtā v2 — Design Spec

**Date:** 2026-10-11 · **Author:** Tarun Theegela · **Status:** Draft for review

## 1. Purpose

Vārtā v2 turns the VARTA course project (a Streamlit geopolitical "terminal") into a personal finance and investing advisor with an AI agent, in the spirit of Origin (useorigin.com). It has two audiences:

- **Owner (Tarun):** real accounts via Plaid, private, used day to day.
- **Recruiters:** a public demo with realistic fake data that shows the full product and the agent working.

Primary goal: a portfolio piece for AI Engineer / Forward Deployed Engineer roles. The agent, its tools, and its evals are the centerpiece. A slice of hardening (tests, CI, clean module boundaries) comes with the rebuild.

**Not in scope:** registered-adviser claims, trade execution, moving money, multi-user accounts, a mobile app. The UI carries a "Not financial advice" footer.

**Success criteria**
1. The demo URL works for a stranger with no login: every page has data, and the advisor answers the four suggested prompts with correct, cited numbers.
2. The owner instance shows Tarun's real accounts, bills calendar, and holdings, and is reachable only over Tailscale.
3. `evals/RESULTS.md` compares at least two models (local Ollama vs OpenRouter) on 25 tasks: pass rate, latency, cost.
4. CI is green: ruff, pytest, web typecheck and build.

## 2. Architecture

```
VPS (Docker Compose; profiles: owner | demo; same images)
├── caddy    TLS. demo → public domain; owner → bound to Tailscale IP only
├── web      Next.js (UI generated in v0), calls api only
├── api      FastAPI: REST + SSE chat stream
├── worker   same image as api, different command; scheduled jobs
└── data     one SQLite file per instance (WAL mode), on a volume

Owner LLM: Ollama on Tarun's Mac (M3 Pro, 18 GB) ⇄ Tailscale ⇄ VPS
Demo LLM:  OpenRouter
Sentiment: TypeSafe Jev (cloud API), both instances
```

Both LLM backends speak the OpenAI-compatible chat API, so the code differs only by `LLM_BASE_URL` and `LLM_MODEL` in each instance's env.

**Repo layout** (this repo; v1 moves to `legacy/`):

```
core/      pure Python library: regime engine, risk metrics, fetchers, normalizers. Polars. No web deps.
api/       FastAPI app: routes, DB, Plaid client, agent loop + tools, scoring client
worker/    job entrypoints (thin; call api/ and core/)
web/       Next.js app (from v0)
evals/     agent + sentiment eval tasks, runner, RESULTS.md
deploy/    compose.yaml, Caddyfile, env templates
legacy/    v1 Streamlit app, frozen, reference only
```

**Decisions**
- SQLite over Postgres: one user per instance, WAL handles the api + worker writer pair, one fewer container. Revisit only if multi-user ever matters.
- The worker is a plain scheduler loop in the api image. No Celery or Redis.
- Polars everywhere in Python. pandas is allowed in exactly one adapter (`core/prices.py`) that converts yfinance output with `pl.from_pandas`.
- Course-era locks (Streamlit, "no cloud API", the 12-asset universe) are retired. CLAUDE.md is rewritten for v2.

## 3. Data model and Plaid

**Plaid facts (verified 2026-10-11 in Plaid docs)**
- Environments: Sandbox (free, fake data) and Production. New US teams created on or after Apr 15 2026 get a Trial plan with **10 real Production Items free**. Removed Items do not free slots.
- `/transactions/sync`: cursor-based, returns `added` / `modified` / `removed`. Loop while `has_more`. On `TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION`, restart from the first page's cursor.
- `/transactions/recurring/get`: streams with `merchant_name`, `frequency` (WEEKLY, BIWEEKLY, SEMI_MONTHLY, MONTHLY, ANNUALLY, UNKNOWN), `average_amount`, `last_amount`, `last_date`, `predicted_next_date` (nullable), `status` (MATURE, EARLY_DETECTION, TOMBSTONED, UNKNOWN), `is_active`. It is an **add-on that needs an access request**, works best with 180+ days of history, and sandbox support is not stated.

- Trial plan products (billing docs): Transactions and Investments are included; **Recurring Transactions is not listed**. Fidelity may need a separate institution-access request.

**Recurring detection: own detector is primary** (keeps the owner instance on the free Trial): a small detector over `transactions`: same merchant, regular cadence (≥3 hits within ±3 days of a weekly/monthly/annual period), `next = last_date + period`. `/transactions/recurring/get` is used only if access is later granted.

**Tables**
```
items              item_id PK, access_token_enc, institution, txn_cursor, status, last_synced_at
accounts           account_id PK, item_id, name, type, subtype, mask, balance_current, balance_available, currency
transactions       txn_id PK, account_id, date, amount, merchant, pfc_primary, pfc_detailed, pending
securities         security_id PK, ticker, name, type
holdings           account_id, security_id, quantity, cost_basis, value, as_of
recurring_streams  stream_id PK, account_id, direction, kind(subscription|bill|income), merchant,
                   avg_amount, last_amount, frequency, last_date, predicted_next_date, status, is_active
budgets            pfc_primary PK, monthly_limit
goals              id PK, name, target_amount, target_date, account_ids
networth_snapshots date PK, assets, liabilities
news_items         id PK, published_at, source, url, title, text, tickers, topics, url_hash, title_hash
news_scores        news_id, ticker, sentiment, sentiment_conf, material, stress, event, noise, raw_json, scored_at
alerts             id PK, created_at, kind, text, action_label, action_href, dismissed
briefings          date PK, items_json, model, generated_at
agent_messages     id PK, conversation_id, role, content, tool_calls, model, latency_ms, tokens_in, tokens_out
```

`recurring_streams.kind` separates subscriptions from bills (rent, utilities, phone, insurance) so the UI can show both without mixing totals. The rule is in code: Plaid category RENT_AND_UTILITIES, LOAN_PAYMENTS, or insurance means `bill`; otherwise `subscription`.

**Sync job (worker, every 6 h plus a "Sync now" button)**
1. `/transactions/sync` loop per item; persist cursor.
2. `/accounts/get` for cached balances. Not the billed real-time `/accounts/balance/get`.
3. `/investments/holdings/get`.
4. `/transactions/recurring/get`.
5. Write a `networth_snapshots` row.

The demo instance runs the same code against Sandbox Items and is wiped and re-seeded nightly.

**Security (owner instance)**
- Access tokens are encrypted at rest with Fernet; the key lives in env.
- Tokens are never logged, never returned by the API, never passed to the LLM. The agent sees only derived data.
- The owner instance has no public route; it is reachable over Tailscale only.

## 4. Advisor agent

**Loop:** hand-written, using the `openai` SDK with `base_url` from env. Call the model, execute the requested tools, append the results, repeat. Maximum 8 tool rounds, then a final streamed answer over SSE. No LangChain or LangGraph: about 100 lines that can be explained end to end.

**Tools (read-only, compact JSON)**
| Tool | Returns |
|---|---|
| `get_net_worth(days)` | snapshots, current assets / liabilities |
| `get_cash_flow(months)` | income vs spend per month |
| `get_spending(period, group_by)` | totals by category or merchant |
| `get_budget_status()` | budget vs actual, this month |
| `get_upcoming_bills(days)` | recurring streams due in window |
| `get_subscriptions()` | active subscriptions, monthly-normalized, price-increase flag |
| `get_goals()` | progress, on-track projection |
| `get_holdings()` | positions, weights, concentration |
| `get_portfolio_risk()` | volatility, max drawdown, beta vs SPY, top weight (core/) |
| `get_market_regime()` | Normal / Elevated / Crisis + component signals (core/, from v1) |
| `get_news(tickers?, topic?, days)` | scored news items with ids |
| `get_sentiment(ticker or topic, days)` | daily sentiment, news vs Reddit separately |

No write tools. The agent cannot trade, move money, or edit budgets. Write actions with a confirm step are a later option.

**Grounding rules (system prompt; checked by evals)**
- Every number in an answer must come from a tool result.
- Every news claim cites `news_items.id`; the UI renders these as source chips.
- When data is missing, say so. Never estimate a balance or a price.
- A small context header goes into the system prompt: today's date, regime label, net worth, bills due this week.

**Proactive outputs (worker)**
- Daily briefing at 07:00 local: the same loop with a fixed prompt; writes `briefings` and the Home "highest impact" card. On the owner instance it runs only if Ollama is reachable; otherwise it is marked pending and retried hourly.
- Alerts: rule-based, no LLM. Bill due in ≤4 days, subscription price up, budget >80%, regime change, holding sentiment flips. Written to `alerts`; Home renders them as the alert feed.

**Models:** set in config, never in code. Owner: an Ollama model with tool-calling support that fits in 18 GB (target 8–14B), chosen by eval results. Demo: an OpenRouter model id.

**Evals (`evals/`)**
- About 25 YAML tasks: a question plus checks, run against a fixed seeded demo DB.
- Checks:
  - required tools were called
  - numbers in the answer match ground truth computed from the DB (with tolerance)
  - no invented tickers or merchants
  - every news claim cites a real id
  - optional LLM-judge score for advice quality
- The runner writes `evals/RESULTS.md`: per model, pass rate, p50/p95 latency, tokens, cost.
- CI runs only the deterministic checks against recorded responses. Live runs are manual.

**Logging:** every turn goes to `agent_messages`. No trace UI in v2.

## 5. News and public sentiment

**Sources**
| Source | Signal | Day one? | Notes |
|---|---|---|---|
| Alpaca news (Benzinga) | ticker news, primary | yes | v1 code; per-article `symbols`; rate limit and plan not stated in docs, confirm when building |
| Finnhub | ticker news, backup | yes | v1 code |
| RSS (WSJ, MarketWatch) | macro | yes | v1 code |
| GDELT | geopolitical + tone | yes | feeds the regime story |
| SEC EDGAR | 8-K filings for holdings | yes | v1 code |
| Polymarket (Gamma API) | crowd odds, macro and geopolitical | yes | `/markets` 300 req / 10 s (official docs); we use a few per run |
| Reddit | retail crowd sentiment | after approval | ~100 req/min per OAuth client (third-party sources; official page unreachable). New apps may need manual approval taking 2–4 weeks. Non-commercial free tier. Store title, link, and scores only, not full post bodies |

**Pipeline (worker, every 15 min)**
1. Fetch and normalize to `{source, url, title, text, published_at}`.
2. Dedupe by `url_hash` and normalized `title_hash`.
3. Tag tickers and topics deterministically: use the source's symbols when given, otherwise match against `securities` plus aliases and the v1 geopolitical keyword list.
4. Score each (item, ticker) pair with **TypeSafe Jev** in one `system_one` call:

```python
state = {"item": {"source": ..., "title": ..., "text": ...}, "ticker": "NVDA", "company": "NVIDIA"}
questions = {
  "sentiment": Score("How does this item bear on `ticker`'s near-term outlook?",
                     ["clearly negative", "somewhat negative", "neutral or mixed",
                      "somewhat positive", "clearly positive"]),
  "material":  Noul("Does `item` contain information that could plausibly move `ticker`'s price?"),
  "stress":    Score("How much geopolitical or market stress does `item` describe?",
                     ["none", "localized", "regional or sector-wide", "systemic"]),
  "event":     Choice("What kind of event is this?",
                      {"earnings": None, "guidance": None, "regulation": None, "geopolitical": None,
                       "supply_chain": None, "m&a": None, "macro": None, "other": None}),
  "noise":     Noul("Is `item` a joke, meme, or low-information post?"),
}
```

5. Policy lives in code, so it can change without re-scoring: drop items with `noise > 0.7` or `material < 0.3` (initial thresholds, tuned on real data). Daily sentiment per ticker is the confidence-weighted mean of `sentiment`, kept separately for news and Reddit. `stress` is shown next to the regime signal. Raw probabilities are stored in `news_scores.raw_json`.
6. Retention: 90 days.

**Privacy:** only public text plus a ticker symbol is sent to TypeSafe. No amounts or account data. The set of tickers Tarun follows is the one thing that leaks; accepted.

**Sentiment eval:** about 100 hand-labeled headlines; report Jev agreement next to the agent evals.

**Cost and access:** third-party reports put Jev at about $0.04 per million input tokens, with output free and no free tier. TypeSafe's direct API is waitlisted, but Jev is reported as available through OpenRouter. At roughly 450 scoring calls a day × 600 tokens, that is under $1/month. **Open items:** confirm price and rate limits with TypeSafe, and whether the SDK's `system_one` call can be routed through OpenRouter, before sub-project 4.

## 6. UI

Generated in v0: chat "VARTA v2 — UI" (`sGWEk7apDEm`). Next.js App Router, TypeScript, Tailwind, shadcn/ui, Recharts. All data comes from `lib/types.ts` and `lib/mock-data.ts`, to be replaced by a typed client generated from FastAPI's OpenAPI schema (`openapi-typescript`).

**Visual system (Origin-leaning)**
- Near-black `#0a0a0a`; cards `#141414`, 1px white-6% border, radius 20px, generous whitespace.
- Monochrome first: white primary buttons with small all-caps mono labels ("SEE ADVICE →"). Calm blue `#4f8cff` for progress; green and red only for meaning.
- Instrument Serif for titles and hero numbers with one italic word; Inter for body; IBM Plex Mono for amounts and section labels.
- Logo: serif wordmark **"Vār*tā*"** (italic last syllable); collapsed mark "V*ā*" in a rounded square; same mark as favicon.
- Slim left sidebar: Home, Advisor, Spending, Bills, Investments, Accounts, News, Goals; regime badge and Settings at the bottom.

**Pages**
| Route | Content |
|---|---|
| `/` | serif greeting, "highest impact" card, alert feed, Cash flow / Spending / Reserves advice cards, financial-health ring with 3 actions, net-worth chart, upcoming bills |
| `/advisor` | full chat with conversation list; drawer version available on every page |
| `/spending` | budget ring (left to spend), category bars, cash-flow card, top merchants |
| `/bills` | month calendar grid with merchant avatars and daily totals, click a day for details; separate **Subscriptions** and **Bills** lists and totals; price-up and possibly-cancelled flags |
| `/investments` | KPIs, holdings table with sentiment sparkline, allocation, risk card, news-vs-Reddit sentiment chart with regime shading |
| `/accounts` | institutions and accounts, Plaid Link button, sync status |
| `/news` | scored feed with chips, source and ticker filters, Polymarket "crowd odds" panel |
| `/goals` | progress cards with on-track projection |
| `/settings` | LLM backend status, data source status, budgets editor |

**Known UI fixes, applied when the UI is pulled into `web/`:** the sentiment sparkline column is empty on `/investments`; bills calendar avatars are too small and all the same colour; the subscriptions total currently mixes bills in (fixed by `kind`); the Home hero card is oversized.

The demo instance shows a slim "Demo — Plaid Sandbox data, resets nightly. Not financial advice." bar.

## 7. Hardening, testing, deploy

**v1 port**
- v1 is frozen in `legacy/`. Port into `core/` only what v2 uses: the regime engine (`regime_live.py` thresholds and weights, `regime.py`) and the fetchers listed in §5 plus prices.
- Not ported: Kronos, DCF, the scenario tab, Alpaca trading. Their known bugs go with them.
- Port rules: no Streamlit imports in `core/`; no network at import time; signal math is a pure function over price frames, with fetching separate.
- **Parity test:** the ported regime function returns the same label and probability as the legacy function for the same input frames (a fixture built from `data/demo/prices.csv`).

**Testing (pytest only)**
- `core/`: regime engine, risk metrics, subscription/bill normalizer, monthly normalization, dedupe, recurring fallback detector (if built).
- `api/`: FastAPI `TestClient` on a temporary SQLite DB; Plaid, Alpaca, TypeSafe and LLM responses replayed from recorded JSON fixtures. No live network in tests.
- Agent: the deterministic eval checks on recorded responses run in CI.
- `web/`: `tsc --noEmit` and `next build`.
- CI: GitHub Actions running ruff, pytest, and pnpm typecheck/build.

**Deploy**
- One small VPS. Hetzner shared 2 vCPU / 4 GB is roughly €4–8/month after its 2026 price changes; check the live price at order time.
- Docker Compose profiles `owner` and `demo`. Caddy for TLS. Tailscale on the VPS; owner Caddy site bound to the Tailscale IP.
- Secrets: per-instance `.env` on the server, `chmod 600`, never committed, never logged.
- **Demo cost guard:** per-IP chat rate limit (20 messages/hour) and a spend cap on the OpenRouter key.
- Backups: nightly `sqlite3 .backup` to a volume. Plaid remains the source of truth for financial data.
- Monitoring: `/healthz`, structured JSON logs, UptimeRobot on the demo URL.

## 8. Build order

Each sub-project gets its own implementation plan and is verified before the next begins.

1. **Foundation:** repo layout, `legacy/` move, `core/` port + parity test, FastAPI skeleton with `/healthz`, SQLite schema, CI, new CLAUDE.md.
2. **Web:** pull the v0 UI into `web/`, apply the known UI fixes, run on mock data, set up the typed API client.
3. **Accounts:** Plaid Link + sync. Accounts, Spending, Bills, Goals, and net worth switch to real data.
4. **News + sentiment:** sources, dedupe, tagging, Jev scoring. News page and Investments sentiment switch to real data.
5. **Agent + evals:** tool loop, SSE chat, briefing, alerts, `evals/RESULTS.md`.
6. **Deploy:** VPS, compose, Caddy, Tailscale, demo seed and nightly reset, rate limit.

**External signups (Tarun, start now; some have review delays):** Plaid team (Trial) plus recurring add-on request; Reddit API app; TypeSafe key; OpenRouter key with a spend cap; Alpaca and Finnhub keys (existing).

## 9. Risks

| Risk | Mitigation |
|---|---|
| Recurring Transactions not on Plaid Trial | own detector is primary (§3) |
| Reddit approval slow or denied | Reddit is optional; Polymarket is the day-one crowd signal |
| Local 8–14B model too weak at tool calling | evals decide; owner can switch model, or opt into OpenRouter for non-sensitive prompts later |
| Mac asleep, so owner agent offline | dashboards, calendar and sync keep working; chat shows "advisor offline"; briefing retries |
| Demo LLM abuse or cost | rate limit plus OpenRouter spend cap |
| Real financial data exposure | Tailscale-only owner, encrypted tokens, no tokens to LLM, owner and demo DBs separate |
