import { test } from "node:test"
import assert from "node:assert/strict"
import { clearLinkSession, linkEventPayload, loadLinkSession, saveLinkSession } from "../lib/plaid-link.ts"

function memoryStorage() {
  const m = new Map<string, string>()
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) }
}

test("link session survives a round trip and clears", () => {
  const s = memoryStorage()
  assert.equal(loadLinkSession(s), null)
  saveLinkSession(s, { token: "link-1", itemId: null })
  assert.deepEqual(loadLinkSession(s), { token: "link-1", itemId: null })
  saveLinkSession(s, { token: "link-2", itemId: "item-9" })
  assert.deepEqual(loadLinkSession(s), { token: "link-2", itemId: "item-9" })
  clearLinkSession(s)
  assert.equal(loadLinkSession(s), null)
})

test("loadLinkSession tolerates junk and missing storage", () => {
  const s = memoryStorage()
  s.setItem("varta.plaid.link", "{not json")
  assert.equal(loadLinkSession(s), null)
  s.setItem("varta.plaid.link", JSON.stringify({ itemId: "x" }))
  assert.equal(loadLinkSession(s), null)
  assert.equal(loadLinkSession(null), null)
})

test("linkEventPayload keeps only telemetry fields, never tokens", () => {
  const p = linkEventPayload("EXIT", {
    link_session_id: "sess-1", institution_id: "ins_3", error_type: "ITEM_ERROR", error_code: "INVALID_CREDENTIALS",
    view_name: "CREDENTIAL", request_id: "req-1", public_token: "public-x", error_message: "bad password",
  })
  assert.deepEqual(p, {
    event: "EXIT", link_session_id: "sess-1", institution_id: "ins_3", error_type: "ITEM_ERROR",
    error_code: "INVALID_CREDENTIALS", view_name: "CREDENTIAL", request_id: "req-1",
  })
  assert.deepEqual(linkEventPayload("OPEN", {}), {
    event: "OPEN", link_session_id: null, institution_id: null, error_type: null, error_code: null, view_name: null, request_id: null,
  })
})
