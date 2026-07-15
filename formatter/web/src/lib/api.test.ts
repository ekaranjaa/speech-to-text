import { afterEach, describe, expect, it, vi } from "vitest"
import { api } from "./api"

afterEach(() => vi.restoreAllMocks())

describe("api.listProfiles", () => {
  it("GETs /api/profiles", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{ id: "clean-verbatim", name: "Clean", description: "" }]), { status: 200 }),
    )
    vi.stubGlobal("fetch", fetchMock)
    const profiles = await api.listProfiles()
    expect(fetchMock).toHaveBeenCalledWith("/api/profiles")
    expect(profiles[0].id).toBe("clean-verbatim")
  })
})

describe("api.exportSegments", () => {
  it("POSTs and returns blob + filename from Content-Disposition", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("SRT", { status: 200, headers: { "Content-Disposition": 'attachment; filename="transcript.srt"' } }),
    )
    vi.stubGlobal("fetch", fetchMock)
    const { filename } = await api.exportSegments([], "srt")
    expect(filename).toBe("transcript.srt")
  })
})

describe("api.formatSegments", () => {
  it("yields turns parsed from the NDJSON stream", async () => {
    const body =
      '{"speaker":"A","start":0,"end":1,"text":"HI"}\n{"speaker":"B","start":1,"end":2,"text":"YO"}\n'
    const fetchMock = vi.fn().mockResolvedValue(new Response(body, { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)
    const got: string[] = []
    for await (const turn of api.formatSegments([], "clean-verbatim")) got.push(turn.speaker)
    expect(got).toEqual(["A", "B"])
  })
})
