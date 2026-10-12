import { test } from "node:test"
import assert from "node:assert/strict"
import { AVATAR_COLORS, avatarColor, avatarInitial } from "../lib/avatar.ts"

const MERCHANTS = ["Rent", "Spotify", "iCloud", "Gym", "ChatGPT", "Con Edison", "Netflix",
  "Verizon", "Car insurance", "Amazon Prime", "The Atlantic", "Dropbox"]

test("initial is trimmed and uppercased", () => {
  assert.equal(avatarInitial("  dropbox"), "D")
  assert.equal(avatarInitial("iCloud"), "I")
  assert.equal(avatarInitial("Ōura"), "Ō")
  assert.equal(avatarInitial("   "), "?")
})

test("color is deterministic and from the palette", () => {
  for (const m of MERCHANTS) {
    assert.equal(avatarColor(m), avatarColor(m))
    assert.ok(AVATAR_COLORS.includes(avatarColor(m)))
  }
})

test("mock merchants spread across at least 6 colors", () => {
  assert.ok(new Set(MERCHANTS.map(avatarColor)).size >= 6)
})

test("color ignores case and surrounding spaces", () => {
  assert.equal(avatarColor("  Netflix "), avatarColor("netflix"))
})
