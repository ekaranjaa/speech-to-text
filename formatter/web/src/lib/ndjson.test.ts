import { describe, expect, it } from "vitest"
import { createNdjsonParser } from "./ndjson"

describe("createNdjsonParser", () => {
  it("emits objects on complete lines and holds partials", () => {
    const p = createNdjsonParser()
    expect(p.push('{"a":1}\n{"b":2')).toEqual([{ a: 1 }])
    expect(p.push("}\n")).toEqual([{ b: 2 }])
    expect(p.flush()).toEqual([])
  })

  it("flush emits a trailing partial object", () => {
    const p = createNdjsonParser()
    expect(p.push('{"a":1}')).toEqual([])
    expect(p.flush()).toEqual([{ a: 1 }])
  })
})
