import { test } from "node:test"
import assert from "node:assert/strict"
import { sparklinePath } from "../lib/sparkline.ts"

test("empty input gives empty path", () => {
  assert.equal(sparklinePath([], 80, 32), "")
})

test("path spans the width and never contains NaN", () => {
  for (const values of [[0.5], [0.2, 0.2, 0.2], [0.7, 0.6, 0.4, 0.2, -0.1, -0.3, -0.5]]) {
    const d = sparklinePath(values, 80, 32)
    assert.ok(!d.includes("NaN"), d)
    assert.ok(d.startsWith("M"), d)
  }
})

test("highest value is drawn at the top, lowest at the bottom", () => {
  const d = sparklinePath([1, 0], 80, 32, 2)
  assert.equal(d, "M2 2 L78 30")
})

test("flat series sits at mid-height", () => {
  assert.equal(sparklinePath([3, 3], 80, 32, 2), "M2 16 L78 16")
})
