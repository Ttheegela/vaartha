/** Idle auto-lock timer: pure, driven by an injected clock so it survives sleep and throttled tabs.
 * Tabs share the last-activity time through a store (localStorage), because they share one session. */

export const AUTH_IDLE_MINUTES = 15 // matches the API default (api/settings.py AUTH_IDLE_MINUTES)
export const IDLE_TIMEOUT_MS = AUTH_IDLE_MINUTES * 60_000
export const IDLE_CHECK_MS = 15_000
export const IDLE_WRITE_MS = 5_000 // throttle for shared-store writes; far below the timeout
export const IDLE_STORAGE_KEY = "varta:last-activity"

/** Shared last-activity time (ms since epoch). */
export type IdleStore = { get(): number | null; set(t: number): void }
type MiniStorage = Pick<Storage, "getItem" | "setItem">

/** IdleStore over a Storage; every access is try/catch-safe (blocked or private storage → no sharing). */
export function storageStore(getStorage: () => MiniStorage | null): IdleStore {
  return {
    get() {
      try {
        const t = Number(getStorage()?.getItem(IDLE_STORAGE_KEY))
        return Number.isFinite(t) && t > 0 ? t : null
      } catch { return null }
    },
    set(t) {
      try { getStorage()?.setItem(IDLE_STORAGE_KEY, String(t)) } catch { /* no sharing */ }
    },
  }
}

/** Timer that calls `onIdle` once when `check()` runs `timeoutMs` after the latest activity in any tab. */
export function createIdleTimer({ timeoutMs, now, onIdle, store }: { timeoutMs: number; now: () => number; onIdle: () => void; store?: IdleStore }) {
  let last = 0
  let written = -Infinity
  let stopped = false
  const reset = () => {
    if (stopped) return
    last = now()
    if (store && last - written >= IDLE_WRITE_MS) { store.set(last); written = last }
  }
  reset()
  return {
    reset,
    check() {
      if (stopped) return
      const t = now()
      const stored = store?.get() ?? 0
      const shared = stored <= t ? stored : 0 // ignore future timestamps: they'd postpone the lock forever
      if (t - Math.max(last, shared) >= timeoutMs) { stopped = true; onIdle() }
    },
    stop() { stopped = true },
  }
}

export const LOCK_STORAGE_KEY = "varta:locked"

/** Tell the other tabs (via the `storage` event) that this tab locked the shared session. */
export function markLocked(storage: MiniStorage | null, t: number): void {
  try { storage?.setItem(LOCK_STORAGE_KEY, String(t)) } catch { /* no sharing */ }
}

/** True for a `storage` event announcing a lock from another tab. */
export function isLockEvent(e: { key: string | null }): boolean {
  return e.key === LOCK_STORAGE_KEY
}
