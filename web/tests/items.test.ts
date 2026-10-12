import { test } from "node:test"
import assert from "node:assert/strict"
import { institutionStatus } from "../lib/items.ts"

const items = [
  { item_id: "a", institution: "Chase", last_synced_at: "2026-10-10T10:00:00Z", status: "active" },
  { item_id: "b", institution: "Chase", last_synced_at: "2026-10-11T10:00:00Z", status: "login_required" },
  { item_id: "c", institution: "Fidelity", last_synced_at: null, status: "active" },
]
test("institutionStatus", () => {
  assert.deepEqual(institutionStatus(items, "Chase"), { lastSyncedAt: "2026-10-11T10:00:00Z", needsLogin: true })
  assert.deepEqual(institutionStatus(items, "Fidelity"), { lastSyncedAt: null, needsLogin: false })
  assert.deepEqual(institutionStatus(items, "Nope"), { lastSyncedAt: null, needsLogin: false })
})
