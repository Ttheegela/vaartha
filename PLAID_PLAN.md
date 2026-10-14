# PLAID_PLAN — Vārtā v2

Rule IDs below are Plaid build-kit guidance IDs (GUIDE-019: cite them here, not in user-facing copy).

## Goal

Workflow: `wf_e50f084c49b83dd9`.

Bring Vārtā's existing Plaid integration in line with Plaid's build-kit guidance before the owner
instance links real (Production) banks: correct product slots, OAuth redirect handling on web, update
mode for broken logins, Link telemetry, and fixes for rule violations found in the existing sync code.

Two instances, one codebase:
- **owner**: Tarun's real accounts, Plaid Production (Trial), FastAPI + Next.js on the Mac, reachable
  only over Tailscale (`tailscale serve`, HTTPS).
- **demo**: public, Heroku, Plaid Sandbox, rate-limited.

Platform: Python FastAPI backend calling Plaid over plain httpx (`api/plaid_client.py`, `api/sync.py`,
routes in `api/main.py`); Next.js web with `react-plaid-link` 5.0.0
(`web/components/link-account-button.tsx`, `web/app/oauth-return/page.tsx`). US only.

## Scope

| Product | Slot | Why |
|---|---|---|
| Transactions | `products` | Spending, bills, cash flow: the first screen needs it (CONV-001, TXN-010). |
| Investments (holdings) | `additional_consented_products` | Consent now, billed on first `/investments/holdings/get`, no institution cut (INV-015, LIAB-007 pattern, CONV-002, TXN-021). Was `required_if_supported_products` (bills at creation where supported, forces the grant at OAuth banks). |

Not in scope, with reasons:
- **identity_verification**: not entitled, and it verifies strangers; Vārtā has one known user. Also mutually exclusive with other products in one Link session (CONV-017).
- **identity_match**: declined by the user.
- **liabilities**: declined for now. Can be added later through update mode with `additional_consented_products` (TXN-020); adding it to the consent list now was not approved.
- **Recurring Transactions add-on** (`/transactions/recurring/get`): entitled in production (dashboard products list includes `recurring_transactions`). Add-later candidate (TXN-016/017, GUIDE-016). Today the own detector in `core/recurring.py` is primary; `days_requested` is already 730 (above the 180-day minimum TXN-017 asks for), so switching later needs no relink.
- Money movement (auth, transfer), signal, income: none.
- Webhook receiver: not built (see Decisions made and Human tasks).

## Human tasks

State per TASK-001. Dashboard read via Plaid MCP for client `6accc9d0aa9e99000cfa9697` on 2026-10-14:
authorized_environments [production, sandbox]; production US products include transactions,
investments, recurring_transactions; redirect_uris empty; webhooks empty; no trial entries listed.

| # | Task | Where | Why | State |
|---|---|---|---|---|
| H1 | Put the correct Production secret in the owner env file (`~/.config/vaartha/owner.env`, `PLAID_SECRET`). The previously pasted value was rejected; Plaid secrets are 30 characters. Restart the owner instance afterwards (PITFALL-003). | https://dashboard.plaid.com → Developers → Keys | Without it every Production call fails with INVALID_API_KEYS. | needs_human |
| H2 | Register the owner OAuth redirect URI `https://<mac>.<tailnet>.ts.net/oauth-return` (exact, no wildcard) in Production, then set `PLAID_REDIRECT_URI` to the same value. Requires Tailscale running on the Mac (`tailscale serve --bg 3000`). | https://dashboard.plaid.com → Developers → API → Allowed redirect URIs (Production) | OAuth banks (Chase, BofA, PNC...) need it; a missing redirect silently hides them or breaks mid-flow (GUIDE-011, OAUTH-001/002, TASK-003). | needs_human |
| H3 | Complete the company profile and the data-security questionnaire. | https://dashboard.plaid.com → Settings → Company profile, and the security questionnaire under the production access / compliance settings | Chase and PNC are gated on them; a gap shows as the bank missing from Link, not an error (OAUTH-008, TASK-006/009). | cannot_verify (not readable through the tools) |
| H4 | Data Transparency Messaging / Link customization in Production: use case set, consent covers Transactions and Investments. | https://dashboard.plaid.com → Link → Data Transparency Messaging / Link customization (Production) | Incomplete DTM fails `/link/token/create` with INVALID_LINK_CUSTOMIZATION, and DTM limits data to consented products (PITFALL-002, CONV-011, TASK-008). | cannot_verify |
| H5 | Webhook receiver URL | https://dashboard.plaid.com → Developers → Webhooks | Owner has no public URL (Tailscale only) so Plaid cannot deliver webhooks; demo is sandbox data reset on a schedule. Sync is a 6-hourly poll plus the Sync button, recorded here as an explicit stopgap (WEBHOOK-005). Revisit if the owner moves to a public host. | not_applicable |

## Implementation checklist

- [x] Investments in `additional_consented_products`, not `required_if_supported_products` (INV-015, CONV-002). `api/main.py`, `api/plaid_client.py`.
- [x] Optional `PLAID_REDIRECT_URI` setting: https only, rejects wildcard, query and fragment (OAUTH-001); sent on every `/link/token/create`, update mode included (OAUTH-002/005). `api/settings.py`.
- [x] Update mode: `POST /api/plaid/link_token {item_id}` creates a token with the stored access_token, no products, plus redirect_uri (ITEM-003, OAUTH-005). The access token never leaves the server (GUIDE-002). Refused (409) for items removed at Plaid.
- [x] Update-mode success does not exchange again; it re-syncs (ITEM-003).
- [x] Accounts page shows Reconnect for `login_required` items.
- [x] Items needing user action (`ITEM_LOGIN_REQUIRED`, `INVALID_CREDENTIALS`, `ITEM_LOCKED`, `ACCESS_NOT_GRANTED`) become `login_required` (ITEM-003/004). `api/sync.py`.
- [x] `ITEM_NOT_FOUND` purges the stored access token, marks the item `not_found`, and later syncs skip it (ITEM-005).
- [x] Web OAuth: link_token persisted in localStorage before Link opens (OAUTH-004, DATA-004); `/oauth-return` re-initializes with the same token and `receivedRedirectUri` = full URL and opens without a click (OAUTH-003/010, WEB-004, WEB-022).
- [x] Link script loaded once per page before `usePlaidLink` mounts, fixing the StrictMode double embed; Link pre-initializes on page load and opens on click (CONV-003, WEB-001, WEB-020/021).
- [x] Link telemetry: onEvent/onExit/onSuccess metadata (link_session_id, institution_id, event/view name, error_type/error_code, request_id) posted to `POST /api/plaid/link_event` through an allowlist and logged as JSON; no tokens (CONV-014/015, WEB-003, WEB-007, GUIDE-006).
- [x] onExit distinguishes abandonment (no error, no message) from errors; shows `display_message` only when non-null (WEB-003, ITEM-002).
- [x] Duplicate bank check before exchange: `institution_id` from onSuccess metadata vs stored items; 409 without exchanging (ITEM-001, ITEM-011).
- [x] `institution_id` stored per item (DATA-001), from `/accounts/get`.
- [x] Plaid `request_id` and `error_type` captured on errors; `request_id` logged with sync failures (ITEM-002, DATA-006).
- [x] Account currency falls back to `unofficial_currency_code` (TXN-005, INV-009).
- [ ] Human tasks H1–H4.

## Rules checked against existing code

| Rule | Outcome |
|---|---|
| GUIDE-001 keys server-side | OK: env vars only, sent as headers, `repr=False` in Settings; test asserts the secret is not in the body. |
| GUIDE-002 access_token server-side | OK: Fernet-encrypted at rest, never in responses; update-mode route test asserts it is not in the response. |
| GUIDE-003 trusted backend | OK: all Plaid calls in FastAPI. |
| GUIDE-004 / WEB-005 one environment source | OK: `PLAID_ENV` picks the base URL; Link uses only the server-minted link_token. Demo is forced to sandbox. |
| GUIDE-005 no Development env | OK: only sandbox and production hosts. |
| GUIDE-006 never log tokens | OK: logs carry item_id, error code, request_id; telemetry is allowlisted on both client and server (extra fields dropped). |
| GUIDE-010/013/015 exchange immediately, persist first | OK: exchange then insert+commit before the first sync. |
| GUIDE-016 add-ons | OK: no add-on endpoints called. Recurring add-on is entitled but unused (decision below). |
| GUIDE-017 institution display data | Acceptable: name comes from `/accounts/get`'s item on every sync, not from Link metadata, so it does not go stale. No logos used. |
| PITFALL-001 / CONV-001 minimal `products` | OK after the change: transactions only. |
| PITFALL-005 / ITEM-004 / ITEM-013 retries | Acceptable: no in-process retry loop; a failed item is reported and retried on the next 6-hourly sync or a manual Sync. No tight loops. 429-specific backoff not added (one user, a handful of items). |
| DATA-001 server state | Fixed: institution_id added. access_token encrypted, item_id, account_ids, cursor stored. |
| DATA-002/003/004 client state | OK: only the link_token (OAuth resume) client-side, cleared on success/exit; public_token exchanged at once. |
| DATA-007 / TXN-002 pagination | OK: all pages buffered, cursor and data written in one transaction after `has_more` is false; test covers failure on page 3 saving nothing. |
| TXN-001 sync only | OK: `/transactions/sync`; no `/transactions/get`. |
| TXN-004 added/modified/removed | OK: upsert by transaction_id, removed deleted. pending_transaction_id reconcile not needed (no user edits/tags on transactions). |
| TXN-005 sign | OK: positive = money out preserved. Fixed currency fallback on accounts. |
| TXN-006 PFC | Partial: uses `personal_finance_category` primary/detailed; confidence_level unused (no auto-apply UI); taxonomy version not pinned. Open question below. |
| TXN-007 restart on mutation | OK: restarts from the starting cursor, up to 3 times; tested. |
| TXN-008 empty first sync | OK: handled; no "importing history" UI (open question). |
| TXN-009 / TXN-017 days_requested | OK: 730 at first initialization. |
| TXN-010 freshness | Stopgap: 6-hourly poll + manual button (see H5). No `/transactions/refresh`. |
| TXN-011 count 500 | OK. |
| TXN-012 account_id mutability | Open: accounts Plaid stops returning are not flagged (STATUS open item 2). |
| TXN-013 / TXN-023 merchant_name nulls | OK: falls back to `name` only for display when merchant_name is null. |
| TXN-019 account-level cursor | N/A: item-level stream only. |
| TXN-020 / INV-013 consent | OK: investments consented at Link via additional_consented_products. `ADDITIONAL_CONSENT_REQUIRED` from holdings is treated as "no investments" for items linked before this change. |
| TXN-022 sync has no item | OK: item health comes from `/accounts/get` errors. |
| INV-001/010 holdings + securities join | OK: `/investments/holdings/get`, securities stored and joined on security_id. |
| INV-002 sandbox custom user | N/A: demo seeds via `/sandbox/public_token/create` with `initial_products` [transactions, investments]. |
| INV-005/012 investment transactions | N/A: not called (holdings only), so no Investments Transactions subscription is started. |
| INV-007/009 pricing and optional fields | OK: institution_value stored; missing fields tolerated via `.get`. |
| ITEM-001 / ITEM-011 duplicates | Fixed: pre-exchange institution check. |
| ITEM-002 branch on codes, log request_id | Fixed: request_id/error_type captured; branching is on error_code. |
| ITEM-003 update mode | Fixed (see checklist). |
| ITEM-005 ITEM_NOT_FOUND / item_remove | Fixed purge; `/item/remove` on disconnect already in `scripts/remove_item.py`. |
| ITEM-007 NO_ACCOUNTS | N/A: no account filters. |
| ITEM-009 enum tolerance | OK: unknown codes pass through as strings. |
| ITEM-012 duplicate displacement | Mitigated by the duplicate check; not detected separately. |
| ITEM-014 no fan-out after exchange | OK: sequential accounts → sync → holdings. |
| OAUTH-001..005, 010 | Fixed (see checklist). OAUTH-006/011 N/A (web only). |
| OAUTH-007 no iframe/webview | OK: Link opens from the top-level page. |
| OAUTH-009 consent expiry | Deferred with webhooks: PENDING_DISCONNECT arrives only by webhook. The resulting ITEM_LOGIN_REQUIRED is caught on sync. |
| WEBHOOK-* | not_applicable (H5). |
| WEB-001/020/021/022 | Fixed (see checklist). |
| WEB-002 exchange response | OK: returns item_id only. |
| WEB-006 CSP | N/A: no CSP header is set. If one is added, allow cdn.plaid.com (script-src, frame-src). |
| CONV-005..009 | Not adopted: single known user (phone pre-fill, routing number, Embedded Search add little). |

## Acceptance

- `uv run pytest -q && uv run ruff check .` pass; `cd web && pnpm typecheck && pnpm test && pnpm build` pass.
- Sandbox (demo): Link opens once (no "embedded more than once"), First Platypus Bank with user_good / pass_good reaches `/api/plaid/exchange` and the Accounts page fills in.
- Sandbox OAuth: Platypus OAuth Bank (ins_127287) with `PLAID_REDIRECT_URI` set to a registered https URL returns to `/oauth-return` and completes (OAUTH-008). Proves mechanics only.
- Update mode: after `/sandbox/item/reset_login`, Accounts shows Reconnect; finishing Link turns the item active on the next sync (SANDBOX-004).
- Production: H1–H4 done, then a real bank (non-OAuth first, then Chase) links on the owner instance.
- `build_check_acceptance` re-run on this exact code before calling it working (GUIDE-014).

Latest verdict (2026-10-14, this code): **FAIL on human tasks only** — CHECK-007 (redirect URI not
registered, H2) and CHECK-009 (H1/H2 needs_human, H3/H4 cannot_verify). All 13 other checks passed or
not_applicable. Evidence: API booted against Sandbox and every new endpoint answered (link_token 200,
unknown item 404, update mode 200, link_event 204, bad public token 502, duplicate bank 409, sync 200);
sandbox personas user_good (14 accounts, 13 holdings, 394 transactions, 9 recurring streams) and
user_transactions_dynamic (7 accounts, 392 transactions); reset_login → login_required → update-mode
token 200.

Fix round 1 (2026-10-14): browser click-through on Sandbox passed (coordinator: new link → onSuccess →
exchange → sync → 14 accounts; this round: Reconnect on a reset_login item opened Link straight at the
bank, onSuccess re-synced without an exchange, item back to active, one link-initialize.js tag and one
Plaid iframe throughout, saved session cleared; `/oauth-return` with an invalid saved token shows "Start
again from Accounts"). API log had no token strings. Removed-item double counting covered by
`test_removed_item_not_double_counted_after_relink`.

Verdict after fix round 1: FAIL on CHECK-007 and CHECK-009 (open human tasks) and CHECK-003. CHECK-003
failed because a browser-inspection script during verification printed one Sandbox update-mode
link_token (read from localStorage) into the agent transcript. No client_id, secret or access_token was
exposed. Link tokens cannot be rotated; this one was Sandbox-only and expired 30 minutes after creation.
Future browser checks must report whether the saved session exists, never its value.

## Maintenance

- Any later change to Plaid-touching code: consult build guidance first and re-run acceptance (GUIDE-014).
- `react-plaid-link` and link-initialize.js: Link JS always loads from the CDN (WEB-010); keep `react-plaid-link` updated via Dependabot.
- Sandbox items go ITEM_LOGIN_REQUIRED on their own after ~30 days (SANDBOX-004): the demo reset reseeds; that also exercises the Reconnect path.
- Link telemetry lives in the API's JSON logs (`logger: varta.plaid_link`); use link_session_id / request_id with Plaid support.
- Rotating the Plaid secret does not invalidate access tokens; if a token leaks, call `/item/access_token/invalidate` (GUIDE-018).

## How to test

- Unit/route tests (no network, `api/plaid_fake.py`): `uv run pytest -q tests/test_plaid_client.py tests/test_plaid_routes.py tests/test_sync.py tests/test_crypto_settings.py`.
- Web pure logic: `cd web && pnpm test` (`tests/plaid-link.test.ts`, `tests/items.test.ts`).
- Manual sandbox: run the API with the sandbox env and `pnpm dev`, open `/accounts`, Link account → First Platypus Bank → user_good / pass_good. Check the API log for `varta.plaid_link` lines (OPEN ... HANDOFF, ON_SUCCESS).
- Manual OAuth: register an https redirect (e.g. the Tailscale URL), set `PLAID_REDIRECT_URI`, link Platypus OAuth Bank, confirm the return to `/oauth-return` finishes the link.
- Manual update mode: `/sandbox/item/reset_login` on the item, Sync now, then Reconnect.

## Decisions made

- **Investments slot**: `additional_consented_products` (user-approved, INV-015).
- **Webhooks**: not built. Owner is Tailscale-only (no public receiver possible); polling every 6 h plus a Sync button is the explicit stopgap (WEBHOOK-005). Recorded as H5.
- **Route paths** (GUIDE-020, proposed defaults, approved with the scope): OAuth return page `/oauth-return`; update mode reuses `POST /api/plaid/link_token` with an optional `{item_id}` body; telemetry at `POST /api/plaid/link_event`.
- **Update-mode body** omits `products` (and the `transactions` options and consented products) instead of sending `products: []` as ITEM-003 words it. Both request no new products; Plaid Sandbox accepted the omitted form on 2026-10-14 (after `/sandbox/item/reset_login`).
- **Telemetry storage**: JSON log lines only, no DB table (CONV-015 asks to store metadata server-side; logs satisfy it for one user).
- **Link script loading**: the app loads link-initialize.js itself (once, module-level promise) and mounts `usePlaidLink` only after it is present, so react-plaid-link's loader finds the existing tag and never re-inserts it.
- **Redirect URI validation**: https only, even in sandbox (Plaid would allow http://localhost there); no wildcard, query or fragment.
- **Reconnect codes**: ITEM_LOGIN_REQUIRED, INVALID_CREDENTIALS, ITEM_LOCKED, ACCESS_NOT_GRANTED all surface as `login_required` → Reconnect.
- **ITEM_NOT_FOUND**: token purged, holdings dropped, transaction/account history kept until the user runs `scripts/remove_item.py`. Accounts of such items are left out of every total (accounts, spending, budgets, goals, recurring, net-worth snapshots, and the advisor tools that read those endpoints) through one shared SQL predicate (`LIVE_ACCOUNT` in `api/sync.py`), so re-linking the bank (new account_ids) does not double count. The Accounts page shows "Removed at bank — link again".
- **One Plaid handler per page**: `PlaidLinkProvider` owns it. "Link account" pre-initializes on page load (CONV-003, WEB-001); Reconnect fetches its update-mode token only on click, takes over the handler (the old one is destroyed first, WEB-011) and opens it, then the new-link handler comes back with a fresh token.
- **Demo rate limits**: `/api/plaid/link_token` has its own per-IP budget (20/h) separate from exchange/sync (5/h), so page loads cannot starve the exchange after a visitor finishes Link. `/api/plaid/link_event` has its own 120/h and rejects bodies over 4 KB (413) before parsing.
- **Accepted risk (demo)**: any demo visitor can request a Reconnect (update-mode) link token for any sandbox item_id. Sandbox only, rate-limited, and the response is a link_token, never an access_token; the owner instance is Tailscale-only.
- **Dedupe granularity**: one item per `institution_id` (stored at exchange time from Link's onSuccess metadata, then refreshed from `/accounts/get`). ITEM-011's finer check (persistent_account_id, else account mask + subtype) is deferred: one user, one login per bank. Comment at the dedupe in `api/main.py`.
- **Demo has no redirect URI**: `PLAID_REDIRECT_URI` is unset on Heroku (sandbox, non-OAuth test banks only); documented in `deploy/heroku.md`.
- **Recurring**: own detector stays primary; Plaid Recurring Transactions is an add-later candidate.

## Open questions

1. Pin the personal_finance_category taxonomy version (v1 vs v2) to match the client's enablement date (TXN-006)? Needs the enablement date; `core/` category mappings must be checked against the chosen list.
2. Flag or hide accounts Plaid no longer returns (TXN-012; STATUS open item 2).
3. Show an "importing history" state after linking (TXN-008)? Without webhooks it would key off `transactions_update_status` from the sync response.
4. Switch subscriptions/bills to Plaid Recurring Transactions now that it is entitled (TXN-016)?
5. Real OAuth return (a bank redirect back to `/oauth-return`) is untested until the redirect URI is registered (H2); Sandbox Platypus OAuth Bank is the first check after that.
