function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

function inlineMdToHtml(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
}

export function mdToHtml(md: string): string {
  const paras = md
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)
  return paras.map((p) => `<p>${inlineMdToHtml(p)}</p>`).join("")
}

export function htmlToMd(html: string): string {
  const paras = [...html.matchAll(/<p>(.*?)<\/p>/gs)].map((m) => m[1])
  const blocks = paras.length ? paras : [html]
  return blocks
    .map((p) =>
      p
        .replace(/<(strong|b)>(.*?)<\/\1>/gs, "**$2**")
        .replace(/<(em|i)>(.*?)<\/\1>/gs, "*$2*")
        .replace(/<[^>]+>/g, "")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&amp;/g, "&")
        .trim(),
    )
    .join("\n\n")
    .trim()
}
