import { test } from "node:test"
import assert from "node:assert/strict"
import { createIdleTimer } from "../lib/idle.ts"

function clock() {
  let t = 1_000
  return { now: () => t, advance: (ms: number) => { t += ms } }
}

test("fires once after the timeout, not before", () => {
  const c = clock(); let fired = 0
  const timer = createIdleTimer({ timeoutMs: 100, now: c.now, onIdle: () => { fired++ } })
  c.advance(99); timer.check(); assert.equal(fired, 0)
  c.advance(1); timer.check(); assert.equal(fired, 1)
  c.advance(500); timer.check(); assert.equal(fired, 1)
})

test("reset defers the deadline", () => {
  const c = clock(); let fired = 0
  const timer = createIdleTimer({ timeoutMs: 100, now: c.now, onIdle: () => { fired++ } })
  c.advance(80); timer.reset()
  c.advance(80); timer.check(); assert.equal(fired, 0)
  c.advance(20); timer.check(); assert.equal(fired, 1)
})

test("stop cancels", () => {
  const c = clock(); let fired = 0
  const timer = createIdleTimer({ timeoutMs: 100, now: c.now, onIdle: () => { fired++ } })
  timer.stop(); c.advance(1_000); timer.check(); assert.equal(fired, 0)
})

import { storageStore } from "../lib/idle.ts"

function fakeStorage() {
  const m = new Map<string, string>()
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v) } }
}

test("tabs sharing a store: activity in B keeps A from firing; both fire after the timeout with no activity", () => {
  const c = clock(); const storage = fakeStorage(); const fired: string[] = []
  const store = storageStore(() => storage)
  const a = createIdleTimer({ timeoutMs: 15 * 60_000, now: c.now, onIdle: () => fired.push("a"), store })
  const b = createIdleTimer({ timeoutMs: 15 * 60_000, now: c.now, onIdle: () => fired.push("b"), store })
  c.advance(10 * 60_000); b.reset()
  c.advance(10 * 60_000); a.check(); b.check()
  assert.deepEqual(fired, [])
  c.advance(5 * 60_000); a.check(); b.check()
  assert.deepEqual(fired, ["a", "b"])
})

test("a future stored timestamp can't postpone the lock forever", () => {
  const c = clock(); const storage = fakeStorage(); let fired = 0
  const t = createIdleTimer({ timeoutMs: 100, now: c.now, onIdle: () => { fired++ }, store: storageStore(() => storage) })
  storage.setItem("varta:last-activity", String(Number.MAX_SAFE_INTEGER)) // another tab with a skewed clock
  c.advance(100); t.check(); assert.equal(fired, 1)
})

test("storageStore survives blocked or throwing storage", () => {
  const boom = () => { throw new Error("blocked") }
  for (const s of [storageStore(() => null), storageStore(boom), storageStore(() => ({ getItem: boom, setItem: boom }))]) {
    assert.equal(s.get(), null)
    s.set(5)
  }
  const c = clock(); let fired = 0
  const t = createIdleTimer({ timeoutMs: 100, now: c.now, onIdle: () => { fired++ }, store: storageStore(boom) })
  c.advance(100); t.check(); assert.equal(fired, 1)
})

import { LOCK_STORAGE_KEY, markLocked, isLockEvent } from "../lib/idle.ts"

test("markLocked writes the shared lock key; isLockEvent matches only it", () => {
  const storage = fakeStorage()
  markLocked(storage, 1234)
  assert.equal(storage.getItem(LOCK_STORAGE_KEY), "1234")
  assert.equal(isLockEvent({ key: LOCK_STORAGE_KEY }), true)
  assert.equal(isLockEvent({ key: "varta:last-activity" }), false)
  assert.equal(isLockEvent({ key: null }), false) // storage.clear()
})

test("markLocked survives blocked storage", () => {
  markLocked({ getItem: () => null, setItem: () => { throw new Error("blocked") } }, 1)
  markLocked(null, 1)
})
