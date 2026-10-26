import { describe, expect, it } from "vitest"
import { htmlToMd, mdToHtml } from "./md"

describe("mdToHtml", () => {
  it("wraps paragraphs and converts emphasis", () => {
    expect(mdToHtml("I loved *Friends*.")).toBe("<p>I loved <em>Friends</em>.</p>")
    expect(mdToHtml("**Hi** there")).toBe("<p><strong>Hi</strong> there</p>")
    expect(mdToHtml("a\n\nb")).toBe("<p>a</p><p>b</p>")
  })
})

describe("htmlToMd", () => {
  it("converts emphasis and paragraphs back to markdown", () => {
    expect(htmlToMd("<p>I loved <em>Friends</em>.</p>")).toBe("I loved *Friends*.")
    expect(htmlToMd("<p><strong>Hi</strong> there</p>")).toBe("**Hi** there")
    expect(htmlToMd("<p>a</p><p>b</p>")).toBe("a\n\nb")
  })
})

describe("round trip", () => {
  it("is stable", () => {
    const md = "First *para* here.\n\nSecond **bold** one."
    expect(htmlToMd(mdToHtml(md))).toBe(md)
  })
})
