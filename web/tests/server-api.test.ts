import { test } from "node:test"
import assert from "node:assert/strict"
import { visitorCookieHeader } from "../lib/server-api.ts"

test("visitorCookieHeader forwards only a 32-hex id", () => {
  const id = "0123456789abcdef0123456789abcdef"
  assert.equal(visitorCookieHeader(id), `varta_vid=${id}`)
  assert.equal(visitorCookieHeader(undefined), undefined)
  assert.equal(visitorCookieHeader("short"), undefined)
  assert.equal(visitorCookieHeader(id.toUpperCase()), undefined)
  assert.equal(visitorCookieHeader(`${id}; evil=1`), undefined)
})
