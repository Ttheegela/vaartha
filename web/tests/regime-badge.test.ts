import { test } from "node:test"
import assert from "node:assert/strict"
import { regimeBadge } from "../lib/regime-badge.ts"

test("maps API labels to badge text and tone", () => {
  assert.deepEqual(regimeBadge({ label: "Normal" }), { text: "NORMAL REGIME", tone: "normal" })
  assert.deepEqual(regimeBadge({ label: "Elevated" }), { text: "ELEVATED REGIME", tone: "elevated" })
  assert.deepEqual(regimeBadge({ label: "Crisis" }), { text: "CRISIS REGIME", tone: "crisis" })
})

test("null means the API failed: never pretend Normal", () => {
  assert.deepEqual(regimeBadge(null), { text: "REGIME UNAVAILABLE", tone: "unavailable" })
})

test("undefined means still loading", () => {
  assert.deepEqual(regimeBadge(undefined), { text: "REGIME …", tone: "loading" })
})

test("unknown label is treated as unavailable", () => {
  assert.equal(regimeBadge({ label: "Weird" }).tone, "unavailable")
})
