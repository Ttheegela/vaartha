import { test } from "node:test"
import assert from "node:assert/strict"
import { apiCookieHeader } from "../lib/auth.ts"

const VID = "0123456789abcdef0123456789abcdef"
const TOKEN = "Ab3_-".repeat(8) + "xyz" // 43 chars, the token_urlsafe(32) shape

test("apiCookieHeader forwards only a 32-hex visitor id", () => {
  assert.equal(apiCookieHeader(VID), `varta_vid=${VID}`)
  assert.equal(apiCookieHeader(undefined), undefined)
  assert.equal(apiCookieHeader("short"), undefined)
  assert.equal(apiCookieHeader(VID.toUpperCase()), undefined)
  assert.equal(apiCookieHeader(`${VID}; evil=1`), undefined)
})

test("apiCookieHeader forwards only a URL-safe 43-char session token", () => {
  assert.equal(apiCookieHeader(undefined, TOKEN), `varta_session=${TOKEN}`)
  assert.equal(apiCookieHeader(VID, TOKEN), `varta_vid=${VID}; varta_session=${TOKEN}`)
  assert.equal(apiCookieHeader(undefined, TOKEN.slice(1)), undefined)
  assert.equal(apiCookieHeader(undefined, `${TOKEN.slice(3)}; a`), undefined)
  assert.equal(apiCookieHeader(undefined, TOKEN.slice(1) + "="), undefined)
})
