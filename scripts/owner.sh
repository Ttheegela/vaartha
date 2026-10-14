#!/usr/bin/env bash
# Run the Vartha owner instance on this Mac: owner.sh start|stop|status|check
# Never prints values from the env file.
set -euo pipefail
# Web port: 3000 is often taken by other local dev tools; override with VAARTHA_WEB_PORT.
WEB_PORT="${VAARTHA_WEB_PORT:-3100}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${VAARTHA_OWNER_ENV:-$HOME/.config/vaartha/owner.env}"
DATA_DIR="$HOME/Library/Application Support/Vaartha"
LOG_DIR="$HOME/Library/Logs/Vaartha"
STANDALONE="$ROOT/web/.next/standalone"

check() {
  if [ ! -f "$ENV_FILE" ]; then
    echo "missing env file: $ENV_FILE" >&2
    return 1
  fi
  local mode
  mode="$(stat -c %a "$ENV_FILE" 2>/dev/null || stat -f %Lp "$ENV_FILE")"
  if [ "$mode" != "600" ]; then
    echo "env file mode is $mode; fix with: chmod 600 \"$ENV_FILE\"" >&2
    return 1
  fi
  local inst
  # Separate bash processes: bash 4+ ignores set -e inside a command substitution in an if/||.
  if ! env -i HOME="$HOME" PATH="$PATH" bash -euc 'set -a; . "$1"' _ "$ENV_FILE" >/dev/null 2>&1; then
    echo "env file is not valid shell; quote values containing spaces" >&2
    return 1
  fi
  inst="$(env -i HOME="$HOME" PATH="$PATH" bash -c 'set -a; . "$1" >/dev/null 2>&1; printf %s "${VARTA_INSTANCE:-owner}"' _ "$ENV_FILE")"
  if [ "$inst" = "demo" ]; then
    echo "VARTA_INSTANCE=demo in env file; the owner instance must not be demo" >&2
    return 1
  fi
  echo "ok: $ENV_FILE"
}

# alive PIDFILE MARKER: pid is live AND its command contains MARKER (guards recycled pids after reboot/crash).
alive() {
  local pid
  [ -f "$1" ] || return 1
  pid="$(cat "$1")"
  if kill -0 "$pid" 2>/dev/null && ps -p "$pid" -o command= 2>/dev/null | grep -qE -- "$2"; then return 0; fi
  rm -f "$1"
  return 1
}

# Next renames its process title to next-server, so match either form.
marker() { case "$1" in api) echo uvicorn ;; *) echo "server.js|next-server" ;; esac; }

start() {
  check
  mkdir -p "$DATA_DIR/backups" "$LOG_DIR"
  local stamp want
  stamp="$ROOT/web/.next/owner-build-stamp"
  want="$(git -C "$ROOT" rev-parse HEAD)-owner"
  if [ ! -f "$STANDALONE/server.js" ] || [ "$(cat "$stamp" 2>/dev/null)" != "$want" ]; then
    # Owner build: same-origin API calls, rewrites to the default http://127.0.0.1:8000.
    (cd "$ROOT" && env -u NEXT_PUBLIC_API_BASE -u API_URL pnpm -C web build)
    rm -rf "$STANDALONE/.next/static"
    echo "$want" >"$stamp"
  fi
  if [ ! -x "$ROOT/.venv/bin/uvicorn" ]; then (cd "$ROOT" && uv sync --locked); fi
  if [ ! -d "$STANDALONE/.next/static" ]; then
    mkdir -p "$STANDALONE/.next"
    cp -R "$ROOT/web/.next/static" "$STANDALONE/.next/static"
  fi
  if [ -d "$ROOT/web/public" ] && [ ! -d "$STANDALONE/public" ]; then
    cp -R "$ROOT/web/public" "$STANDALONE/public"
  fi
  if alive "$DATA_DIR/api.pid" uvicorn; then echo "api already running"; else
    (
      set -a; . "$ENV_FILE"; set +a
      export VARTA_INSTANCE=owner VARTA_DB_PATH="$DATA_DIR/varta.db" \
        VARTA_BACKUP_DIR="$DATA_DIR/backups" RUN_WORKER=1
      unset TRUST_PROXY CORS_ORIGINS COOKIE_DOMAIN
      cd "$ROOT"
      nohup "$ROOT/.venv/bin/uvicorn" --factory api.main:create_app --host 127.0.0.1 --port 8000 \
        >>"$LOG_DIR/api.log" 2>&1 &
      echo $! >"$DATA_DIR/api.pid"
    )
  fi
  if alive "$DATA_DIR/web.pid" "$(marker web)"; then echo "web already running"; else
    (
      cd "$ROOT"
      HOSTNAME=127.0.0.1 PORT="$WEB_PORT" VARTA_INSTANCE=owner \
        nohup node "$STANDALONE/server.js" >>"$LOG_DIR/web.log" 2>&1 &
      echo $! >"$DATA_DIR/web.pid"
    )
  fi
  echo "started: web http://127.0.0.1:$WEB_PORT, api http://127.0.0.1:8000 (logs: $LOG_DIR)"
}

stop() {
  local n
  for n in web api; do
    if alive "$DATA_DIR/$n.pid" "$(marker $n)"; then kill "$(cat "$DATA_DIR/$n.pid")" && echo "stopped $n"; fi
    rm -f "$DATA_DIR/$n.pid"
  done
}

status() {
  local n
  for n in api web; do
    if alive "$DATA_DIR/$n.pid" "$(marker $n)"; then echo "$n: running (pid $(cat "$DATA_DIR/$n.pid"))"
    else echo "$n: stopped"; fi
  done
  curl -s 127.0.0.1:8000/healthz || echo "healthz: no response"
  echo
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  check) check ;;
  *) echo "usage: owner.sh start|stop|status|check" >&2; exit 2 ;;
esac
