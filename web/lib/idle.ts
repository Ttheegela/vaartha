/** Idle auto-lock timer: pure, driven by an injected clock so it survives sleep and throttled tabs. */

export const AUTH_IDLE_MINUTES = 15 // matches the API default (api/settings.py AUTH_IDLE_MINUTES)
export const IDLE_TIMEOUT_MS = AUTH_IDLE_MINUTES * 60_000
export const IDLE_CHECK_MS = 15_000

/** Timer that calls `onIdle` once when `check()` runs `timeoutMs` after the last `reset()`. */
export function createIdleTimer({ timeoutMs, now, onIdle }: { timeoutMs: number; now: () => number; onIdle: () => void }) {
  let last = now()
  let stopped = false
  return {
    reset() { if (!stopped) last = now() },
    check() { if (!stopped && now() - last >= timeoutMs) { stopped = true; onIdle() } },
    stop() { stopped = true },
  }
}
