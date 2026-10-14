import { test } from "node:test"
import assert from "node:assert/strict"
import { httpsRedirectUrl } from "../lib/https-redirect.ts"

test("http behind the proxy with force on redirects to https, keeping path and query", () => {
  assert.equal(
    httpsRedirectUrl("http://demo.vaartha.tech/a/b?x=1", "http", true),
    "https://demo.vaartha.tech/a/b?x=1",
  )
})

test("https, missing header, or force off do not redirect", () => {
  assert.equal(httpsRedirectUrl("http://h/a", "https", true), null)
  assert.equal(httpsRedirectUrl("http://h/a", null, true), null)
  assert.equal(httpsRedirectUrl("http://h/a", "http", false), null)
})
