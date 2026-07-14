import { describe, expect, it } from "vitest"
import { groupTurns } from "./turns"

describe("groupTurns", () => {
  it("merges consecutive same-speaker segments, space-joining text", () => {
    const segs = [
      { start: 0, end: 1, speaker: "A", text: "hi" },
      { start: 1, end: 2, speaker: "A", text: "there" },
      { start: 2, end: 3, speaker: "B", text: "yo" },
    ]
    expect(groupTurns(segs)).toEqual([
      { start: 0, end: 2, speaker: "A", text: "hi there" },
      { start: 2, end: 3, speaker: "B", text: "yo" },
    ])
  })

  it("returns [] for no segments", () => {
    expect(groupTurns([])).toEqual([])
  })
})
