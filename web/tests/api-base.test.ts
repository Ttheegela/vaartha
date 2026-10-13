import { test } from "node:test"
import assert from "node:assert/strict"
import { apiUrl } from "../lib/api-base.ts"

test("apiUrl joins base and path without a double slash", () => {
  assert.equal(apiUrl("/api/chat", ""), "/api/chat")
  assert.equal(apiUrl("/api/chat", "https://api.x.dev/"), "https://api.x.dev/api/chat")
  assert.equal(apiUrl("/api/chat", "https://api.x.dev"), "https://api.x.dev/api/chat")
})

test("apiUrl rejects a path without a leading slash", () => {
  assert.throws(() => apiUrl("api/chat", ""))
})
