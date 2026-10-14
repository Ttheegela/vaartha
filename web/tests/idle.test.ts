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
