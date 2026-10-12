export type SSEEvent = { event: string; data: string }

/** Split a text/event-stream buffer into complete events; an unfinished trailing block is returned as `rest`. */
export function parseSSE(buffer: string): { events: SSEEvent[]; rest: string } {
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n")
  const rest = blocks.pop() ?? ""
  const events = blocks.filter(Boolean).map((block) => {
    let event = "message"
    const data: string[] = []
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim()
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""))
    }
    return { event, data: data.join("\n") }
  })
  return { events, rest }
}
