import type { Segment, Turn } from "./types"

export function groupTurns(segments: Segment[]): Turn[] {
  const turns: Turn[] = []
  for (const seg of segments) {
    const last = turns[turns.length - 1]
    if (last && last.speaker === seg.speaker) {
      last.end = seg.end
      last.text = `${last.text} ${seg.text}`.trim()
    } else {
      turns.push({ ...seg })
    }
  }
  return turns
}
