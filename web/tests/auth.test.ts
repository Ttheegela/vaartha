import { test } from "node:test"
import assert from "node:assert/strict"
import { canonicalRedirectUrl, ceremonyErrorMessage, lockPath, needsSession, returnPath, safeNext } from "../lib/auth.ts"

const ORIGIN = "https://taruns-macbook-pro.tail9ec172.ts.net"

test("safeNext keeps same-site relative paths only", () => {
  assert.equal(safeNext("/accounts?x=1"), "/accounts?x=1")
  assert.equal(safeNext("/a/../news?q=1#top"), "/news?q=1#top") // normalized
  for (const bad of [null, "", "accounts", "//evil.com", "/\\evil.com", "https://evil.com", "/a\nb", "/lock", "/lock?next=/x", "javascript:alert(1)", "/.//evil.com", "/a/..//evil.com"])
    assert.equal(safeNext(bad), "/", String(bad))
})

test("lockPath carries the encoded path and query", () => {
  assert.equal(lockPath("/spending?m=1&y=2"), "/lock?next=%2Fspending%3Fm%3D1%26y%3D2")
  assert.equal(lockPath("/"), "/lock")
})

test("needsSession skips lock, api and app assets, but not pages like oauth-return", () => {
  for (const p of ["/", "/accounts", "/oauth-return", "/settings", "/lockdown", "/apis", "/icons", "/iconic-page", "/apple-icons", "/manifest.webmanifest.x"]) assert.equal(needsSession(p), true, p)
  for (const p of ["/lock", "/api/auth/status", "/api/accounts", "/manifest.webmanifest", "/icon.svg", "/icon", "/icon1.png", "/apple-icon.png", "/apple-icon", "/favicon.ico", "/_next/static/x.js"])
    assert.equal(needsSession(p), false, p)
})

test("canonicalRedirectUrl sends other hosts to the passkey origin, never loops on it", () => {
  assert.equal(canonicalRedirectUrl("taruns-macbook-pro.tail9ec172.ts.net", "/a?b=1", ORIGIN), null)
  assert.equal(canonicalRedirectUrl("localhost:3100", "/a?b=1", ORIGIN), `${ORIGIN}/a?b=1`)
  assert.equal(canonicalRedirectUrl("127.0.0.1:3100", "/", ORIGIN), `${ORIGIN}/`)
  assert.equal(canonicalRedirectUrl("TARUNS-MACBOOK-PRO.tail9ec172.ts.net", "/", ORIGIN), null)
  assert.equal(canonicalRedirectUrl("localhost:3100", "/", undefined), null)
  assert.equal(canonicalRedirectUrl(null, "/", ORIGIN), null)
  assert.equal(canonicalRedirectUrl("localhost:3100", "/", "http://localhost:3100"), null)
})

test("ceremonyErrorMessage maps errors to plain words", () => {
  assert.match(ceremonyErrorMessage({ name: "NotAllowedError" }), /cancel/i)
  assert.match(ceremonyErrorMessage({ name: "WebAuthnError", code: "ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED" }), /already/i)
  assert.match(ceremonyErrorMessage({ status: 401 }, false), /set one up/i)
  assert.match(ceremonyErrorMessage({ status: 401 }, true), /couldn't verify/i)
  assert.doesNotMatch(ceremonyErrorMessage({ status: 401 }, true), /set one up/i)
  assert.match(ceremonyErrorMessage({ status: 403 }), /setup code/i)
  assert.match(ceremonyErrorMessage({}), /try again/i)
})

test("returnPath keeps path and query but drops Next's _rsc cache-buster", () => {
  assert.equal(returnPath(new URL("http://h/spending?m=1&_rsc=abc")), "/spending?m=1")
  assert.equal(returnPath(new URL("http://h/accounts?_rsc=abc")), "/accounts")
  assert.equal(returnPath(new URL("http://h/")), "/")
})
