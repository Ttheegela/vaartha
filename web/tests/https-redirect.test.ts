import { test } from "node:test"
import assert from "node:assert/strict"
import { httpsRedirectUrl } from "../lib/https-redirect.ts"

test("http behind the proxy with force on redirects to the public host, keeping path and query", () => {
  assert.equal(
    httpsRedirectUrl("demo.vaartha.tech", "/a/b?x=1", "http", true),
    "https://demo.vaartha.tech/a/b?x=1",
  )
})

test("uses the host header, never the server's own bind address", () => {
  assert.equal(httpsRedirectUrl("demo.vaartha.tech", "/x", "http", true), "https://demo.vaartha.tech/x")
})

test("https, missing proto, force off, or missing host do not redirect", () => {
  assert.equal(httpsRedirectUrl("h", "/a", "https", true), null)
  assert.equal(httpsRedirectUrl("h", "/a", null, true), null)
  assert.equal(httpsRedirectUrl("h", "/a", "http", false), null)
  assert.equal(httpsRedirectUrl(null, "/a", "http", true), null)
})
