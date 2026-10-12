import { test } from "node:test"
import assert from "node:assert/strict"
import { parseSSE } from "../lib/sse.ts"

test("parseSSE one event", () => {
  assert.deepEqual(parseSSE('event: meta\ndata: {"a":1}\n\n'), { events: [{ event: "meta", data: '{"a":1}' }], rest: "" })
})
test("parseSSE two events in one chunk", () => {
  const r = parseSSE("event: tool\ndata: 1\n\nevent: answer\ndata: 2\n\n")
  assert.deepEqual(r.events.map((e) => e.event), ["tool", "answer"])
})
test("parseSSE carries a split event as rest", () => {
  const a = parseSSE("event: answer\ndata: he")
  assert.deepEqual(a, { events: [], rest: "event: answer\ndata: he" })
  assert.deepEqual(parseSSE(a.rest + "llo\n\n").events, [{ event: "answer", data: "hello" }])
})
test("parseSSE joins multi-line data", () => {
  assert.equal(parseSSE("event: answer\ndata: a\ndata: b\n\n").events[0].data, "a\nb")
})
test("parseSSE tolerates CRLF", () => {
  assert.deepEqual(parseSSE("event: done\r\ndata: x\r\n\r\n").events, [{ event: "done", data: "x" }])
})
test("parseSSE defaults event to message", () => {
  assert.equal(parseSSE("data: x\n\n").events[0].event, "message")
})
