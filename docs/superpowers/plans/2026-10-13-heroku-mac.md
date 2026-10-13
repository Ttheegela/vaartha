# Heroku Demo + Mac Owner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the public demo on Heroku (GitHub Student credit, $13/month for 24 months) and the owner instance on Tarun's Mac (reachable from his phone over Tailscale). The VPS/Compose path from `plans/2026-10-12-deploy.md` stays in the repo as an alternative.

**Architecture:**
- **Two Heroku apps on the container stack:**
  - API app: one Basic dyno running uvicorn with the scheduler **embedded** as a background thread. Heroku dynos don't share a disk, so the worker can't be a separate dyno.
  - Web app: the Next standalone image.
- **Browser calls the API directly** at `https://api.<domain>`, with CORS and credentials. Heroku's router then appends the real client IP to `X-Forwarded-For`, so the per-IP limits keep working. Proxying through Next would hide that IP.
- **Shared visitor cookie:** it is scoped to the parent domain, so the server-rendered advisor page on `demo.<domain>` still receives it.
- **Ephemeral disk:** Heroku restarts dynos daily and wipes their disk. The demo DB is therefore re-seeded **at boot whenever it is empty**.
- **Deploys:** a manual GitHub Actions workflow builds both images on amd64 and releases them through the Heroku Container Registry. No Docker on the Mac.
- **Owner on the Mac:** one script runs the API with the embedded worker and the Next standalone server, both bound to `127.0.0.1`.
  - Settings come from `~/.config/vaartha/owner.env`, outside the repo.
  - The DB lives in `~/Library/Application Support/Vaartha/`.
  - `tailscale serve` publishes the web app over HTTPS to Tarun's tailnet only.
  - An optional launchd agent starts it at login.

**Tech Stack:** FastAPI + Starlette CORSMiddleware, stdlib threading, Next.js 16 standalone, GitHub Actions, Heroku Container Registry + Platform API, bash, launchd, Tailscale.

**Spec:** `docs/superpowers/specs/2026-10-11-varta-v2-design.md` §2/§7 (deploy), §4 decision note (OpenRouter for both). This plan supersedes the VPS hosting choice; the decision note is added in Task 5.

## Global Constraints

- Everything from `plans/2026-10-12-deploy.md` Global Constraints still binds:
  - Polars only; docstrings on public functions; named constants.
  - No network or disk side effects at import; no live network in tests.
  - Never read, print or log secrets; never commit env files, `*.db` or `data/`.
  - Conventional Commits with **no Co-Authored-By**.
  - Never push, force-push, or run `ruff format` repo-wide.
  - **Never start Docker** on the Mac.
- Demo limits stay: chat **20/hour per IP**; sync and Plaid link/exchange **5/hour per IP**; dismiss is a no-op on demo.
- Schedules stay as in `worker/schedule.py`.
- New env vars, all optional, with defaults that keep today's behaviour:
  - `RUN_WORKER` (`"1"` → start the embedded scheduler thread; default off)
  - `CORS_ORIGINS` (comma-separated; default empty → no CORS middleware)
  - `COOKIE_DOMAIN` (default unset → host-only cookie)
  - `PORT` (Heroku; default 8000 for the API image)
  - Web build-time `NEXT_PUBLIC_API_BASE` (default `""` → same-origin, as today)
- The owner instance never runs on Heroku and never listens on anything but `127.0.0.1`. Phone access goes only through `tailscale serve`.
- Gate: `uv run pytest -q && uv run ruff check .`; for web, `cd web && pnpm typecheck && pnpm test && pnpm build`. Regenerate `web/openapi.json` + `web/lib/api-types.ts` if the API schema changes.

## Review Focus

1. **Embedded worker:** it must not block or crash the API.
   - Start it only when `RUN_WORKER=1`, from the app lifespan, exactly once per process.
   - Stop it cleanly on shutdown.
   - A job that raises must not kill the thread.
   - Tests and plain `create_app()` calls must never start it.
2. **Boot reseed on Heroku:** an empty demo DB at startup reseeds once, in the worker thread rather than blocking startup. It never runs on owner.
3. **CORS and credentials:**
   - Only the configured origins get `Access-Control-Allow-Origin` with `allow_credentials=True`; never `*` with credentials.
   - The SSE chat still streams cross-origin.
   - A 429 response still carries the CORS headers, so the browser shows the rate-limit message instead of a CORS error.
4. **Client IP on Heroku:** the per-IP limits must key on the real client.
   - With direct browser→API calls, Heroku appends the client IP as the **last** XFF entry, matching `client_ip(trust_proxy=True)`.
   - Any path that proxies `/api` through the web dyno would collapse all visitors into one IP, so production must not route `/api` through Next.
5. **Owner exposure on the Mac:**
   - Both servers bind `127.0.0.1` only.
   - The owner env file lives outside the repo with mode 600.
   - The script never echoes env values.
   - `tailscale serve` (not `funnel`) is the only remote path.

---

### Task 1: API for Heroku (embedded worker, boot reseed, CORS, cookie domain, $PORT)

**Files:**
- Modify: `api/main.py`, `api/settings.py`, `api/advisor.py` (cookie domain), `worker/main.py` (expose a reusable loop), `Dockerfile` (CMD honours `$PORT`)
- Test: `tests/test_embedded_worker.py`, additions to `tests/test_advisor_api.py`, `tests/test_crypto_settings.py`

**Interfaces:**
- Settings:
  - `run_worker: bool` (`RUN_WORKER == "1"`)
  - `cors_origins: tuple[str, ...]` (split on commas, stripped, empties dropped)
  - `cookie_domain: str | None`
- `worker/main.py`:
  - `run_loop(settings, stop: threading.Event, tick_seconds: int = TICK_SECONDS, clock=lambda: datetime.now(UTC)) -> None`. Runs `init_db` once, then until `stop` is set calls `tick` (guarded with `log.exception`) and waits with `stop.wait(tick_seconds)`.
  - `main()` becomes `run_loop` with a SIGTERM-to-stop handler.
  - `boot_reseed_if_empty(settings) -> bool`: on demo, if `accounts` has no rows, run `scripts.reset_demo.reset(settings, local_today(settings.tz))`, then record `app_state` `job:<name>` = now for `demo_reset`, `news`, `alerts` and `briefing` (the reset already did them, so the first tick must not repeat them, especially the paid briefing call), and return True. On owner, or when not empty, return False. Exceptions are logged and return False.
- `create_app`:
  - Uses a FastAPI `lifespan`.
  - When `settings.run_worker`, it starts one daemon thread that runs `boot_reseed_if_empty` and then `run_loop`. On shutdown it sets the stop event and joins with a timeout of `WORKER_JOIN_SECONDS = 5`.
  - It adds `CORSMiddleware(allow_origins=list(cors_origins), allow_credentials=True, allow_methods=["GET","POST"], allow_headers=["content-type"])` **only** when `cors_origins` is non-empty.
- `/api/chat` cookie: pass `domain=settings.cookie_domain` when set.
- `Dockerfile` CMD: `sh -c 'exec uvicorn --factory api.main:create_app --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log'`. Keep the HEALTHCHECK working with `${PORT:-8000}`.

- [ ] **Step 1: Write failing tests**
  - Embedded worker:
    - `create_app` with `run_worker=False` starts no thread; check that `threading.enumerate()` names don't include `"varta-worker"`.
    - With `run_worker=True`, using `TestClient` as a context manager and a monkeypatched `run_loop` that records a call and returns: the thread starts once, and exits on shutdown.
    - `run_loop` with a stop event already set after one tick (a fake `tick` via monkeypatch) calls `tick` once.
    - A `tick` that raises is logged and the loop continues to the next iteration.
  - `boot_reseed_if_empty`:
    - Empty demo DB → reset called, returns True. Monkeypatch `scripts.reset_demo.reset` to avoid Plaid and network.
  - After a boot reseed, `tick` at the same `now` does not run `demo_reset`, `news`, `alerts` or `briefing` again.
    - A non-empty DB, or an owner instance → returns False and reset is not called.
    - Reset raising → returns False and logs.
  - CORS:
    - With `cors_origins=("https://demo.example.dev",)`, a preflight `OPTIONS /api/chat` from that origin returns 200 with `access-control-allow-origin` equal to the origin and `access-control-allow-credentials: true`.
    - An unknown origin gets no allow-origin header.
    - A 429 from the chat limiter (limit 1) carries the allow-origin header for the allowed origin.
    - No CORS headers when `cors_origins` is empty.
  - Cookie: with `cookie_domain=".example.dev"`, the Set-Cookie on the first chat contains `Domain=example.dev` (or `.example.dev`; assert case-insensitively on `domain=`).
  - Settings parse the three new env vars.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Full suite, ruff, OpenAPI regen if needed.**
- [ ] **Step 5: Commit.** `feat(api): embedded scheduler, boot reseed, CORS and cookie domain for Heroku`

---

### Task 2: Web calls the API base (cross-origin capable)

**Files:**
- Create: `web/lib/api-base.ts`, `web/tests/api-base.test.ts`
- Modify: every **browser-side** fetch of `/api/...`. Find them with `grep -rn '"/api\|`/api' web/components web/lib web/app`. Expected at least: `web/lib/api.ts` (getRegime), `web/components/advisor-chat.tsx`, `web/components/advisor-workspace.tsx`, `web/components/alert-feed.tsx`, `web/components/link-account-button.tsx`, `web/components/sync-button.tsx`.
- Modify: `web/Dockerfile` (`ARG NEXT_PUBLIC_API_BASE=""` + `ENV` in the build stage before `pnpm build`)

**Interfaces:**
- `apiUrl(path: string, base = process.env.NEXT_PUBLIC_API_BASE ?? ""): string`:
  - Joins without a double slash: base `"https://api.x.dev/"` + `"/api/chat"` → `"https://api.x.dev/api/chat"`. An empty base returns `path` unchanged.
  - `path` must start with `/`; throw otherwise.
- Every browser fetch uses `fetch(apiUrl("/api/..."), { ..., credentials: "include" })`.
- Server-side `apiGet` (`web/lib/server-api.ts`) is unchanged: it keeps using runtime `API_URL`.

- [ ] **Step 1: Write the failing node test** for `apiUrl`: empty base, trailing slash, no trailing slash, and a bad path that throws.
- [ ] **Step 2: Run `pnpm test`.** Expected: FAIL.
- [ ] **Step 3: Implement and replace the fetch calls.** Check with grep that no browser-side `fetch("/api` remains.
- [ ] **Step 4: `pnpm typecheck && pnpm test && pnpm build`.**
- [ ] **Step 5: Commit.** `feat(web): configurable API base for cross-origin demo`

---

### Task 3: Heroku deploy workflow + Heroku runbook

**Files:**
- Create: `.github/workflows/deploy-heroku.yml`, `deploy/heroku.md`

**Workflow** (`workflow_dispatch` only, never on push):
- Inputs: none. It uses repo **variables** `HEROKU_API_APP`, `HEROKU_WEB_APP`, `NEXT_PUBLIC_API_BASE` and the repo **secret** `HEROKU_API_KEY`.
- Steps:
  - checkout
  - `docker login registry.heroku.com -u _ --password-stdin` with the key
  - build `registry.heroku.com/${HEROKU_API_APP}/web` from `.`
  - build `registry.heroku.com/${HEROKU_WEB_APP}/web` from `web` with `--build-arg NEXT_PUBLIC_API_BASE`
  - push both
  - release each with the Heroku Platform API: `PATCH https://api.heroku.com/apps/<app>/formation` with `{"updates":[{"type":"web","docker_image":"<image id>"}]}`, headers `Accept: application/vnd.heroku+json; version=3` and `Authorization: Bearer $HEROKU_API_KEY`. The image id comes from `docker inspect --format '{{.Id}}'`.
- Never echo the key. `set -euo pipefail` in every `run`.
- Verify the formation-release API shape against Heroku's Container Registry docs ("Releasing an image" via Platform API) before writing it.

**`deploy/heroku.md`** (concise, no secrets, placeholders `<domain>`, `<api-app>`, `<web-app>`):
1. Redeem the Student offer (card required, $13 a month for 24 months), install the Heroku CLI, `heroku login`.
2. Create the apps: `heroku create <api-app> --stack container` and `heroku create <web-app> --stack container`.
3. Set config vars on the API app with `heroku config:set` from **your terminal**:
   - `VARTA_INSTANCE=demo`, `PLAID_ENV=sandbox`, the Plaid sandbox keys, `TOKEN_ENCRYPTION_KEY` (generate locally with `uv run python -m scripts.new_token_key`)
   - the news keys, `OPENROUTER_API_KEY` (demo key with cap), `LLM_BASE_URL`, `LLM_MODEL`
   - `CHAT_RATE_PER_HOUR=20`, `VARTA_TZ`, `TRUST_PROXY=1`, `RUN_WORKER=1`
   - `CORS_ORIGINS=https://demo.<domain>`, `COOKIE_DOMAIN=.<domain>`, `VARTA_DB_PATH=/tmp/varta.db`
4. Set config vars on the web app: `API_URL=https://api.<domain>`, `VARTA_INSTANCE=demo`.
5. GitHub: repo Settings → Secrets → `HEROKU_API_KEY` (from `heroku authorizations:create`). Variables: `HEROKU_API_APP`, `HEROKU_WEB_APP`, `NEXT_PUBLIC_API_BASE=https://api.<domain>`.
6. Run the "deploy-heroku" workflow from the Actions tab.
7. Dynos: `heroku ps:type web=basic -a <api-app>`. For the web app use `eco` (sleeps; total about $12 a month) or `basic` (always on; about $14 a month). Then scale both to 1.
8. Domains:
   - `heroku domains:add api.<domain> -a <api-app>` and `heroku domains:add demo.<domain> -a <web-app>`.
   - At Name.com, add two **CNAME** records pointing at the DNS targets Heroku prints.
   - `heroku certs:auto:enable` on both. ACM is free.
9. Verify:
   - `curl https://api.<domain>/healthz`
   - The demo pages have data, which appears within a minute or two after the first boot (boot reseed).
   - The 21st chat in an hour returns 429.
   - `heroku logs -t -a <api-app>` shows JSON lines.
10. Notes:
   - Conversations reset at the daily dyno restart, and the demo data reseeds then.
   - Watch memory: a Basic dyno has 512 MB. If `heroku logs` shows R14, set `WEB_CONCURRENCY=1`; uvicorn already runs a single worker.
   - The calendar reminders cover the credit end and the domain transfer.

- [ ] **Step 1:** Write both files.
- [ ] **Step 2:** Validate the workflow YAML: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/deploy-heroku.yml'))"`. Run `uv run pytest -q && uv run ruff check .` once.
- [ ] **Step 3: Commit.** `build(deploy): Heroku container release workflow and runbook`

---

### Task 4: Owner instance on the Mac

**Files:**
- Create: `scripts/owner.sh`, `deploy/macos/dev.vaartha.owner.plist.template`, `deploy/owner-mac.md`, `tests/test_owner_script.py` (light: `bash -n` syntax check, and a `--check` mode)

**`scripts/owner.sh`** (bash, `set -euo pipefail`):
- Subcommands: `start | stop | status | check`.
- `ENV_FILE=${VAARTHA_OWNER_ENV:-$HOME/.config/vaartha/owner.env}`. It refuses to run if the file is missing or its mode is not 600, and prints the fix (`chmod 600 ...`). It **never prints values**.
- `DATA_DIR="$HOME/Library/Application Support/Vaartha"`; `LOG_DIR="$HOME/Library/Logs/Vaartha"`.
- `start`:
  - Exports the env file in a subshell (`set -a; . "$ENV_FILE"; set +a`).
  - Forces `VARTA_INSTANCE=owner`, `VARTA_DB_PATH="$DATA_DIR/varta.db"`, `VARTA_BACKUP_DIR="$DATA_DIR/backups"` and `RUN_WORKER=1`, and unsets `TRUST_PROXY`, `CORS_ORIGINS` and `COOKIE_DOMAIN`.
  - Starts `uv run uvicorn --factory api.main:create_app --host 127.0.0.1 --port 8000` in the background, with a pidfile in `$DATA_DIR`.
  - Builds the web if `web/.next/standalone/server.js` is missing (`pnpm -C web build`). It copies `.next/static` into the standalone folder if absent.
  - Starts `HOSTNAME=127.0.0.1 PORT=3000 API_URL=http://127.0.0.1:8000 VARTA_INSTANCE=owner node web/.next/standalone/server.js` in the background, with a pidfile.
  - Logs go to `$LOG_DIR`.
- `stop`: kills via the pidfiles. `status`: shows the pids and `curl -s 127.0.0.1:8000/healthz`.
- `check`: validates the env file exists with mode 600 and that `VARTA_INSTANCE` is not demo, without starting anything. Exits 0 or 1. Tests use it with a temp env file.
- The script resolves the repo root from its own location, so it works from launchd.

**`deploy/macos/dev.vaartha.owner.plist.template`:** a LaunchAgent that runs `<repo>/scripts/owner.sh start` at load (`RunAtLoad`) with `KeepAlive` false and logs to `~/Library/Logs/Vaartha/launchd.log`. `<repo>` is a placeholder the user replaces.

**`deploy/owner-mac.md`:**
1. Create `~/.config/vaartha/owner.env` (`mkdir -p`, `chmod 700` the directory, `chmod 600` the file). List the variables:
   - `PLAID_ENV=production` with the Trial keys, and a new `TOKEN_ENCRYPTION_KEY`
   - the news keys
   - `OPENROUTER_API_KEY` (the owner key with its own cap), `LLM_BASE_URL`, `LLM_MODEL`
   - `VARTA_TZ`
2. `scripts/owner.sh check`, then `scripts/owner.sh start`, then open `http://127.0.0.1:3000`.
3. Phone access: install Tailscale on the Mac and phone, run `tailscale serve --bg 3000`, then open `https://<mac>.<tailnet>.ts.net` on the phone. Only works while the Mac is awake. Never use `tailscale funnel`, which is public.
4. Start at login: copy the plist template to `~/Library/LaunchAgents/`, replace `<repo>`, then `launchctl load ...`.
5. Notes:
   - Jobs catch up on wake.
   - Backups go to `~/Library/Application Support/Vaartha/backups`.
   - Moving to a VPS later works through the backup and `plans/2026-10-12-deploy.md`.

- [ ] **Step 1: Write the failing tests:**
  - `bash -n scripts/owner.sh` exits 0.
  - `owner.sh check` with a missing env file exits 1.
  - With mode 644 it exits 1 and the message mentions `chmod 600`.
  - With mode 600 and `VARTA_INSTANCE=demo` inside, it exits 1.
  - With a valid file it exits 0.
  - The output never contains a value from the file (put a sentinel `SECRET_SENTINEL_123` in it and assert it is absent).
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement the script, template and doc.**
- [ ] **Step 4: Full suite and ruff.**
- [ ] **Step 5: Commit.** `feat(owner): run the owner instance on the Mac with Tailscale serve`

---

### Task 5: Docs (spec decision note, STATUS, CLAUDE.md)

**Files:** `docs/superpowers/specs/2026-10-11-varta-v2-design.md` (§7 decision note), `docs/superpowers/STATUS.md`, `CLAUDE.md`, `deploy/README.md` (one line at the top: "VPS path; the current hosting is Heroku (demo) + Mac (owner): see `deploy/heroku.md`, `deploy/owner-mac.md`").

- §7 decision note (2026-10-13): the demo runs on Heroku (Student credit, 24 months), the owner runs on the Mac with `tailscale serve`, and the VPS/Compose path is kept as the alternative. Include the reasons: cost, and keeping the owner's data local.
- STATUS: the next step is Heroku provisioning with Tarun. Mention the calendar reminders, for the domain transfer around Aug 2027 and the Heroku credit end around Aug 2028.
- [ ] Commit: `docs: Heroku demo + Mac owner hosting decision`

---

### Task 6: Go live (controller, with Tarun)

Not a subagent task; every outward step needs Tarun's go-ahead.
- [ ] Tarun claims `vaartha.dev` on Name.com (Student Pack) and redeems the Heroku offer.
- [ ] Follow `deploy/heroku.md`. Tarun types every secret in his own terminal or in the dashboards.
- [ ] Verify the demo against spec success criterion 1, plus the 429 limit and `/healthz`. Add a Honeybadger uptime check (Student Pack).
- [ ] Owner: `owner.sh check` and `start`, then link a real bank (STATUS open items 1–2), then phone access via Tailscale.
- [ ] Update STATUS, README (demo URL) and memory.
