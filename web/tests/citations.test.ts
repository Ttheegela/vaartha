import { test } from "node:test"
import assert from "node:assert/strict"
import { splitBold, splitCitations } from "../lib/citations.ts"

const sources = [{ id: 40 }, { id: 7 }]
test("known ids become cites numbered by source order", () => {
  assert.deepEqual(splitCitations("A [n:7] b [n:40].", sources), [
    { kind: "text", text: "A " }, { kind: "cite", n: 2, id: 7 },
    { kind: "text", text: " b " }, { kind: "cite", n: 1, id: 40 }, { kind: "text", text: "." },
  ])
})
test("unknown ids are dropped", () => {
  assert.deepEqual(splitCitations("A [n:99] b", sources), [{ kind: "text", text: "A " }, { kind: "text", text: " b" }])
})
test("same id twice gets the same n", () => {
  const cites = splitCitations("[n:7] and [n:7]", sources).filter((s) => s.kind === "cite")
  assert.deepEqual(cites.map((c) => c.n), [2, 2])
})
test("no citations gives one text segment", () => {
  assert.deepEqual(splitCitations("plain", sources), [{ kind: "text", text: "plain" }])
})

test("splitBold marks **bold** runs and keeps the rest", () => {
  assert.deepEqual(splitBold("a **b** c"), [
    { text: "a ", bold: false }, { text: "b", bold: true }, { text: " c", bold: false },
  ])
  assert.deepEqual(splitBold("plain"), [{ text: "plain", bold: false }])
  assert.deepEqual(splitBold("**x**"), [{ text: "x", bold: true }])
  assert.deepEqual(splitBold("2 ** 3"), [{ text: "2 ** 3", bold: false }])
})
