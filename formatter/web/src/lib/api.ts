import { createNdjsonParser } from "./ndjson"
import type { DiarizeResult, Profile, Segment, Turn } from "./types"

async function ensureOk(resp: Response): Promise<Response> {
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(detail.detail || resp.statusText)
  }
  return resp
}

function filenameFrom(resp: Response, fallback: string): string {
  const cd = resp.headers.get("Content-Disposition") || ""
  const m = cd.match(/filename="?([^"]+)"?/)
  return m ? m[1] : fallback
}

export const api = {
  async diarize(file: File, numSpeakers?: number): Promise<DiarizeResult> {
    const form = new FormData()
    form.append("audio", file)
    if (numSpeakers) form.append("num_speakers", String(numSpeakers))
    const resp = await ensureOk(await fetch("/api/diarize", { method: "POST", body: form }))
    return resp.json()
  },

  async listProfiles(): Promise<Profile[]> {
    const resp = await ensureOk(await fetch("/api/profiles"))
    return resp.json()
  },

  async *formatSegments(segments: Segment[], profileId: string): AsyncGenerator<Turn> {
    const resp = await ensureOk(
      await fetch("/api/format/segments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segments, profile_id: profileId }),
      }),
    )
    const parser = createNdjsonParser()
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      for (const obj of parser.push(decoder.decode(value, { stream: true }))) yield obj as Turn
    }
    for (const obj of parser.flush()) yield obj as Turn
  },

  async exportSegments(
    segments: Segment[],
    format: string,
  ): Promise<{ blob: Blob; filename: string }> {
    const resp = await ensureOk(
      await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segments, format }),
      }),
    )
    return { blob: await resp.blob(), filename: filenameFrom(resp, `transcript.${format}`) }
  },
}
