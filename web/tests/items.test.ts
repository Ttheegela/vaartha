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

import { itemsWithoutAccounts } from "../lib/items.ts"
test("itemsWithoutAccounts", () => {
  const all = [
    { item_id: "a", institution: "Chase", last_synced_at: "2026-10-10T10:00:00Z", status: "login_required" },
    { item_id: "c", institution: "Fidelity", last_synced_at: null, status: "active" },
    { item_id: "d", institution: null, last_synced_at: null, status: "login_required" },
    { item_id: "e", institution: "Ally", last_synced_at: "2026-10-10T10:00:00Z", status: "active" },
  ]
  assert.deepEqual(itemsWithoutAccounts(all, ["Ally"]), [
    { id: "a", title: "Chase", badge: "Needs re-login" },
    { id: "c", title: "Fidelity", badge: "Sync failed" },
    { id: "d", title: "Unnamed institution", badge: "Needs re-login" },
  ])
  assert.deepEqual(itemsWithoutAccounts(all, ["Chase", "Fidelity", "Ally"]).map((i) => i.id), ["d"])
  assert.deepEqual(itemsWithoutAccounts([], []), [])
})

import { reconnectItemId } from "../lib/items.ts"
test("reconnectItemId picks the institution's item that needs re-login", () => {
  assert.equal(reconnectItemId(items, "Chase"), "b")
  assert.equal(reconnectItemId(items, "Fidelity"), null)
  assert.equal(reconnectItemId([{ item_id: "z", institution: null, last_synced_at: null, status: "login_required" }], "Unknown"), "z")
})
