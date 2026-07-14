export function createNdjsonParser() {
  let buffer = ""
  const drain = (final: boolean): unknown[] => {
    const out: unknown[] = []
    let idx: number
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).trim()
      buffer = buffer.slice(idx + 1)
      if (line) out.push(JSON.parse(line))
    }
    if (final && buffer.trim()) {
      out.push(JSON.parse(buffer.trim()))
      buffer = ""
    }
    return out
  }
  return {
    push: (text: string) => {
      buffer += text
      return drain(false)
    },
    flush: () => drain(true),
  }
}
