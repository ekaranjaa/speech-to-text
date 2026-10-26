# Formatter Frontend (Subsystem B2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Vue 3 + TypeScript single-page UI for the transcript studio: upload audio → diarize → edit speaker turns in a TipTap WYSIWYG editor (rename speakers, edit text, italics) → format via a style profile → export SRT/VTT/TXT/Markdown. Served as static assets by the existing FastAPI backend (Subsystem B1).

**Architecture:** A Vite project at `formatter/web/`. Pure TypeScript modules (`lib/md.ts`, `lib/turns.ts`, `lib/ndjson.ts`, `lib/api.ts`) hold all logic and are unit-tested with Vitest. Vue components are thin glue over that logic; TipTap uses **HTML** as its content format, and `md.ts` bridges the API's Markdown (`*italics*`) to/from that HTML. The built SPA is served by FastAPI at `/`; profile management stays on the existing v1 Jinja `/manage` page.

**Tech Stack:** Vite 6, Vue 3.5, TypeScript, Tailwind CSS v4 (`@tailwindcss/vite`), shadcn-vue conventions (`cn()` util + reka-ui primitives, hand-added components), TipTap 2 (`@tiptap/vue-3`), Vitest + @vue/test-utils + jsdom.

## Global Constraints

- **Project root `formatter/web/`.** Run npm and Vitest from there. Node ≥ 20.
- **Markdown is the wire format.** The API's segment `text` uses Markdown emphasis (`*italic*`, `**bold**`). TipTap edits **HTML**; `md.ts` converts both ways. Turn state stores Markdown.
- **Segment/Turn shape:** `{ speaker: string; start: number; end: number; text: string }` — identical to B1, so turns POST directly as `segments`.
- **Testable core gets TDD** (`lib/*.ts` via Vitest). **Vue components + TipTap are gated by `npm run build` + a manual browser smoke**, not unit tests.
- **Dev:** Vite proxies `/api` → `http://localhost:8084` (the formatter container). **Prod:** FastAPI serves `formatter/web/dist` at `/`.
- **Do not break B1/v1 backend tests.** The only backend change is Task 6 (serve the SPA + adjust the `/` page test). `/manage` Jinja stays.
- Profile management is out of scope for the SPA (use the existing `/manage` page); the SPA only *lists/selects* profiles.

## File Structure

- `formatter/web/package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.node.json`, `index.html`, `vitest.config.ts`
- `formatter/web/src/main.ts`, `src/App.vue`, `src/style.css`
- `formatter/web/src/lib/cn.ts`, `lib/md.ts`, `lib/turns.ts`, `lib/ndjson.ts`, `lib/api.ts`, `lib/types.ts`
- `formatter/web/src/components/ui/Button.vue`, `components/TurnEditor.vue`, `components/Toolbar.vue`
- `formatter/web/src/lib/*.test.ts` (Vitest)
- `formatter/app/main.py` — **modify** (serve SPA); `formatter/tests/test_pages.py` — **modify**
- `formatter/Dockerfile` — **modify** (multi-stage node build); `.dockerignore` — **modify**

---

### Task 1: Scaffold Vite + Vue + TS + Tailwind + Vitest

**Files:** create the project skeleton under `formatter/web/`.

**Interfaces:** Produces a buildable app and a passing Vitest run. `cn(...classes)` util available.

- [ ] **Step 1: Create `formatter/web/package.json`**

```json
{
  "name": "transcript-studio-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "@tiptap/pm": "^2.10.3",
    "@tiptap/starter-kit": "^2.10.3",
    "@tiptap/vue-3": "^2.10.3",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "lucide-vue-next": "^0.468.0",
    "reka-ui": "^2.0.0",
    "tailwind-merge": "^2.5.5",
    "vue": "^3.5.13"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "@vitejs/plugin-vue": "^5.2.1",
    "@vue/test-utils": "^2.4.6",
    "jsdom": "^25.0.1",
    "tailwindcss": "^4.0.0",
    "typescript": "~5.6.3",
    "vite": "^6.0.5",
    "vitest": "^2.1.8",
    "vue-tsc": "^2.1.10"
  }
}
```

- [ ] **Step 2: Create configs**

`formatter/web/vite.config.ts`:
```ts
import { fileURLToPath, URL } from "node:url"
import vue from "@vitejs/plugin-vue"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { proxy: { "/api": "http://localhost:8084" } },
  build: { outDir: "dist" },
})
```

`formatter/web/vitest.config.ts`:
```ts
import { fileURLToPath, URL } from "node:url"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: { environment: "jsdom", include: ["src/**/*.test.ts"] },
})
```

`formatter/web/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "strict": true,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src/**/*.ts", "src/**/*.vue"]
}
```

`formatter/web/tsconfig.node.json`:
```json
{ "compilerOptions": { "composite": true, "module": "ESNext", "moduleResolution": "bundler", "skipLibCheck": true }, "include": ["vite.config.ts", "vitest.config.ts"] }
```

- [ ] **Step 3: Create app entry + styles**

`formatter/web/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Transcript Studio</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`formatter/web/src/style.css`:
```css
@import "tailwindcss";
```

`formatter/web/src/main.ts`:
```ts
import { createApp } from "vue"
import App from "./App.vue"
import "./style.css"

createApp(App).mount("#app")
```

`formatter/web/src/App.vue` (placeholder, replaced in Task 5):
```vue
<template>
  <main class="mx-auto max-w-3xl p-6">
    <h1 class="text-2xl font-semibold">Transcript Studio</h1>
  </main>
</template>
```

`formatter/web/src/lib/cn.ts`:
```ts
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 4: Add a smoke test** — `formatter/web/src/lib/cn.test.ts`:
```ts
import { describe, expect, it } from "vitest"
import { cn } from "./cn"

describe("cn", () => {
  it("merges and dedupes tailwind classes", () => {
    expect(cn("p-2", "p-4")).toBe("p-4")
    expect(cn("text-sm", false && "hidden", "font-bold")).toBe("text-sm font-bold")
  })
})
```

- [ ] **Step 5: Install and verify**

Run: `cd formatter/web && npm install`
Then: `npm run test`
Expected: 1 test file, 1 passed.

- [ ] **Step 6: Verify build**

Run: `cd formatter/web && npm run build`
Expected: build succeeds, `dist/index.html` produced.

- [ ] **Step 7: Add `.gitignore` for the web project** — `formatter/web/.gitignore`:
```
node_modules/
dist/
```

- [ ] **Step 8: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/web/package.json formatter/web/package-lock.json formatter/web/vite.config.ts formatter/web/vitest.config.ts formatter/web/tsconfig.json formatter/web/tsconfig.node.json formatter/web/index.html formatter/web/src/main.ts formatter/web/src/App.vue formatter/web/src/style.css formatter/web/src/lib/cn.ts formatter/web/src/lib/cn.test.ts formatter/web/.gitignore
git commit -m "feat(web): scaffold Vite + Vue + TS + Tailwind v4 + Vitest"
```

---

### Task 2: Markdown ↔ HTML converters

**Files:** Create `formatter/web/src/lib/md.ts`, `src/lib/md.test.ts`

**Interfaces:** Produces `mdToHtml(md: string): string` and `htmlToMd(html: string): string`, supporting the emphasis subset — `**bold**`↔`<strong>`, `*italic*`↔`<em>`, blank-line-separated paragraphs ↔ `<p>…</p>`.

- [ ] **Step 1: Write the failing test** — `formatter/web/src/lib/md.test.ts`:
```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter/web && npx vitest run src/lib/md.test.ts`
Expected: FAIL — cannot find module `./md`.

- [ ] **Step 3: Write minimal implementation** — `formatter/web/src/lib/md.ts`:
```ts
function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

function inlineMdToHtml(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
}

export function mdToHtml(md: string): string {
  const paras = md.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter/web && npx vitest run src/lib/md.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/web/src/lib/md.ts formatter/web/src/lib/md.test.ts
git commit -m "feat(web): markdown <-> html converters for emphasis subset"
```

---

### Task 3: Turn grouping + types

**Files:** Create `formatter/web/src/lib/types.ts`, `src/lib/turns.ts`, `src/lib/turns.test.ts`

**Interfaces:** Produces `Segment`/`Turn`/`Profile` types and `groupTurns(segments: Segment[]): Turn[]` — contiguous same-speaker runs, `text` space-joined (mirrors the backend). `Turn` and `Segment` are the same shape.

- [ ] **Step 1: Write the failing test** — `formatter/web/src/lib/turns.test.ts`:
```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter/web && npx vitest run src/lib/turns.test.ts`
Expected: FAIL — cannot find module `./turns`.

- [ ] **Step 3: Write minimal implementation**

`formatter/web/src/lib/types.ts`:
```ts
export interface Segment {
  start: number
  end: number
  speaker: string
  text: string
}

export type Turn = Segment

export interface Profile {
  id: string
  name: string
  description: string
}

export interface DiarizeResult {
  segments: Segment[]
  speakers: string[]
  language: string
}
```

`formatter/web/src/lib/turns.ts`:
```ts
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter/web && npx vitest run src/lib/turns.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/web/src/lib/types.ts formatter/web/src/lib/turns.ts formatter/web/src/lib/turns.test.ts
git commit -m "feat(web): segment/turn types + groupTurns"
```

---

### Task 4: NDJSON parser + API client

**Files:** Create `formatter/web/src/lib/ndjson.ts`, `src/lib/ndjson.test.ts`, `src/lib/api.ts`, `src/lib/api.test.ts`

**Interfaces:**
- `createNdjsonParser(): { push(text: string): unknown[]; flush(): unknown[] }` — accumulates chunks, returns completed objects per newline.
- `api`: `diarize(file, numSpeakers?)`, `listProfiles()`, `formatSegments(segments, profileId)` (async generator of `Turn`), `exportSegments(segments, format)` → `{ blob, filename }`.

- [ ] **Step 1: Write the failing tests**

`formatter/web/src/lib/ndjson.test.ts`:
```ts
import { describe, expect, it } from "vitest"
import { createNdjsonParser } from "./ndjson"

describe("createNdjsonParser", () => {
  it("emits objects on complete lines and holds partials", () => {
    const p = createNdjsonParser()
    expect(p.push('{"a":1}\n{"b":2')).toEqual([{ a: 1 }])
    expect(p.push('}\n')).toEqual([{ b: 2 }])
    expect(p.flush()).toEqual([])
  })

  it("flush emits a trailing partial object", () => {
    const p = createNdjsonParser()
    expect(p.push('{"a":1}')).toEqual([])
    expect(p.flush()).toEqual([{ a: 1 }])
  })
})
```

`formatter/web/src/lib/api.test.ts`:
```ts
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
    const body = '{"speaker":"A","start":0,"end":1,"text":"HI"}\n{"speaker":"B","start":1,"end":2,"text":"YO"}\n'
    const fetchMock = vi.fn().mockResolvedValue(new Response(body, { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)
    const got: string[] = []
    for await (const turn of api.formatSegments([], "clean-verbatim")) got.push(turn.speaker)
    expect(got).toEqual(["A", "B"])
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd formatter/web && npx vitest run src/lib/ndjson.test.ts src/lib/api.test.ts`
Expected: FAIL — modules not found.

- [ ] **Step 3: Write minimal implementations**

`formatter/web/src/lib/ndjson.ts`:
```ts
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
```

`formatter/web/src/lib/api.ts`:
```ts
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

  async exportSegments(segments: Segment[], format: string): Promise<{ blob: Blob; filename: string }> {
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd formatter/web && npx vitest run src/lib/ndjson.test.ts src/lib/api.test.ts`
Expected: PASS. (In jsdom, `Response.body.getReader()` is available for the streaming test; if the runtime lacks it, the `formatSegments` test still drives the same parser.)

- [ ] **Step 5: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/web/src/lib/ndjson.ts formatter/web/src/lib/ndjson.test.ts formatter/web/src/lib/api.ts formatter/web/src/lib/api.test.ts
git commit -m "feat(web): NDJSON parser + typed API client"
```

---

### Task 5: UI — upload, editor, format, export

**Files:** Create `formatter/web/src/components/ui/Button.vue`, `components/TurnEditor.vue`, `components/Toolbar.vue`; replace `src/App.vue`.

**Interfaces:** Consumes `api`, `groupTurns`, `mdToHtml`/`htmlToMd`. No new exported logic (glue). Gate: build + manual smoke.

- [ ] **Step 1: Button component** — `formatter/web/src/components/ui/Button.vue`:
```vue
<script setup lang="ts">
import { cn } from "@/lib/cn"
defineProps<{ variant?: "default" | "outline" | "ghost" }>()
const base =
  "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition disabled:opacity-50 disabled:pointer-events-none"
const variants = {
  default: "bg-neutral-900 text-white hover:bg-neutral-800",
  outline: "border border-neutral-300 hover:bg-neutral-100",
  ghost: "hover:bg-neutral-100",
}
</script>
<template>
  <button :class="cn(base, variants[variant ?? 'default'])"><slot /></button>
</template>
```

- [ ] **Step 2: TipTap turn editor** — `formatter/web/src/components/TurnEditor.vue`:
```vue
<script setup lang="ts">
import { watch } from "vue"
import { Editor, EditorContent, useEditor } from "@tiptap/vue-3"
import StarterKit from "@tiptap/starter-kit"
import { htmlToMd, mdToHtml } from "@/lib/md"
import type { Turn } from "@/lib/types"

const props = defineProps<{ turn: Turn }>()
const emit = defineEmits<{ (e: "update", value: Turn): void }>()

const editor = useEditor({
  extensions: [StarterKit],
  content: mdToHtml(props.turn.text),
  onUpdate: ({ editor }: { editor: Editor }) => {
    emit("update", { ...props.turn, text: htmlToMd(editor.getHTML()) })
  },
})

// Re-hydrate when a formatted turn streams in and replaces the text.
watch(
  () => props.turn.text,
  (text) => {
    if (editor.value && htmlToMd(editor.value.getHTML()) !== text) {
      editor.value.commands.setContent(mdToHtml(text), false)
    }
  },
)

function onSpeaker(e: Event) {
  emit("update", { ...props.turn, speaker: (e.target as HTMLInputElement).value })
}
function toggleItalic() {
  editor.value?.chain().focus().toggleItalic().run()
}
</script>
<template>
  <div class="rounded-lg border border-neutral-200 p-3">
    <div class="mb-2 flex items-center gap-2">
      <input
        :value="turn.speaker"
        @input="onSpeaker"
        class="w-48 rounded border border-neutral-300 px-2 py-1 text-sm font-semibold"
      />
      <button class="rounded px-2 py-1 text-sm italic hover:bg-neutral-100" @click="toggleItalic">i</button>
    </div>
    <editor-content :editor="editor" class="prose prose-sm max-w-none focus:outline-none" />
  </div>
</template>
```

- [ ] **Step 3: Toolbar (upload / profile / format / export)** — `formatter/web/src/components/Toolbar.vue`:
```vue
<script setup lang="ts">
import type { Profile } from "@/lib/types"
import Button from "@/components/ui/Button.vue"

defineProps<{ profiles: Profile[]; profileId: string; busy: boolean; canExport: boolean }>()
const emit = defineEmits<{
  (e: "upload", file: File): void
  (e: "update:profileId", value: string): void
  (e: "format"): void
  (e: "export", format: string): void
}>()

function onFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) emit("upload", file)
}
</script>
<template>
  <div class="flex flex-wrap items-center gap-3">
    <label class="cursor-pointer">
      <input type="file" accept="audio/*,video/*" class="hidden" @change="onFile" />
      <span class="inline-flex rounded-md border border-neutral-300 px-4 py-2 text-sm hover:bg-neutral-100">Upload audio</span>
    </label>
    <select
      :value="profileId"
      @change="emit('update:profileId', ($event.target as HTMLSelectElement).value)"
      class="rounded-md border border-neutral-300 px-3 py-2 text-sm"
    >
      <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
    </select>
    <Button :disabled="busy || !canExport" @click="emit('format')">Format</Button>
    <span class="mx-1 h-6 w-px bg-neutral-200" />
    <Button variant="outline" :disabled="!canExport" @click="emit('export', 'srt')">SRT</Button>
    <Button variant="outline" :disabled="!canExport" @click="emit('export', 'vtt')">VTT</Button>
    <Button variant="outline" :disabled="!canExport" @click="emit('export', 'txt')">TXT</Button>
    <Button variant="outline" :disabled="!canExport" @click="emit('export', 'md')">MD</Button>
  </div>
</template>
```

- [ ] **Step 4: App shell wiring** — replace `formatter/web/src/App.vue`:
```vue
<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { api } from "@/lib/api"
import { groupTurns } from "@/lib/turns"
import type { Profile, Turn } from "@/lib/types"
import Toolbar from "@/components/Toolbar.vue"
import TurnEditor from "@/components/TurnEditor.vue"

const profiles = ref<Profile[]>([])
const profileId = ref("")
const turns = ref<Turn[]>([])
const busy = ref(false)
const status = ref("")

const canExport = computed(() => turns.value.length > 0)

onMounted(async () => {
  try {
    profiles.value = await api.listProfiles()
    if (profiles.value.length) profileId.value = profiles.value[0].id
  } catch (e) {
    status.value = `Could not load profiles: ${(e as Error).message}`
  }
})

async function onUpload(file: File) {
  busy.value = true
  status.value = "Diarizing… (first run downloads models on the host)"
  try {
    const result = await api.diarize(file)
    turns.value = groupTurns(result.segments)
    status.value = `${result.speakers.length} speaker(s), ${turns.value.length} turns.`
  } catch (e) {
    status.value = `Error: ${(e as Error).message}`
  } finally {
    busy.value = false
  }
}

async function onFormat() {
  busy.value = true
  status.value = "Formatting…"
  try {
    const segments = turns.value.map((t) => ({ ...t }))
    const formatted: Turn[] = []
    for await (const turn of api.formatSegments(segments, profileId.value)) {
      formatted.push(turn)
      turns.value = [...formatted]
    }
    status.value = "Done."
  } catch (e) {
    status.value = `Error: ${(e as Error).message}`
  } finally {
    busy.value = false
  }
}

async function onExport(format: string) {
  try {
    const { blob, filename } = await api.exportSegments(turns.value.map((t) => ({ ...t })), format)
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    status.value = `Error: ${(e as Error).message}`
  }
}

function updateTurn(i: number, value: Turn) {
  turns.value[i] = value
}
</script>
<template>
  <main class="mx-auto max-w-4xl space-y-5 p-6">
    <header>
      <h1 class="text-2xl font-semibold">Transcript Studio</h1>
      <p class="text-sm text-neutral-500">
        Upload audio → diarize → edit speakers &amp; text → format → export.
        <a href="/manage" class="underline">Manage profiles</a>
      </p>
    </header>

    <Toolbar
      :profiles="profiles"
      v-model:profileId="profileId"
      :busy="busy"
      :can-export="canExport"
      @upload="onUpload"
      @format="onFormat"
      @export="onExport"
    />

    <p v-if="status" class="text-sm text-neutral-600">{{ status }}</p>

    <section class="space-y-3">
      <TurnEditor
        v-for="(turn, i) in turns"
        :key="i"
        :turn="turn"
        @update="(v) => updateTurn(i, v)"
      />
      <p v-if="!turns.length" class="text-sm text-neutral-400">No transcript yet. Upload an audio file to begin.</p>
    </section>
  </main>
</template>
```

- [ ] **Step 5: Type-check + build**

Run: `cd formatter/web && npm run build`
Expected: `vue-tsc` type-checks clean and Vite build succeeds.

- [ ] **Step 6: Run the full Vitest suite (no regressions)**

Run: `cd formatter/web && npm run test`
Expected: all `lib/*.test.ts` pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/web/src/App.vue formatter/web/src/components
git commit -m "feat(web): upload/diarize/edit/format/export UI"
```

---

### Task 6: Serve the SPA from FastAPI + multi-stage Docker

**Files:** Modify `formatter/app/main.py`, `formatter/tests/test_pages.py`, `formatter/Dockerfile`, `formatter/.dockerignore`

**Interfaces:** FastAPI serves `formatter/web/dist` at `/` when present (SPA). `/manage` Jinja + `/static` unchanged. All `/api/*` routes take precedence (registered before the mount).

- [ ] **Step 1: Serve the SPA** — in `formatter/app/main.py`, add near the other mounts (inside `create_app`, AFTER all `/api/*` routes and the `/manage` route are declared, just before `return app`):
```python
    web_dist = _APP_DIR.parent / "web" / "dist"
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="spa")
```
Then remove the old Jinja `/` route (`format_page`) and its `format.html` usage. Keep the `/manage` route.

- [ ] **Step 2: Update the page test** — replace `formatter/tests/test_pages.py` with:
```python
from app.config import Config
from app.main import create_app


def _cfg(tmp_path):
    return Config(
        ollama_host="x", model="m", temperature=0.2, max_chunk_words=800,
        profiles_dir=str(tmp_path), diarizer_host="x",
    )


def test_manage_page_renders(tmp_path):
    from fastapi.testclient import TestClient

    client = TestClient(create_app(_cfg(tmp_path)))
    resp = client.get("/manage")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_root_is_spa_or_absent(tmp_path):
    # The SPA at "/" is only mounted when web/dist exists (built in CI/Docker).
    # In a bare test env it's absent; either way "/" must not 500.
    from fastapi.testclient import TestClient

    client = TestClient(create_app(_cfg(tmp_path)))
    resp = client.get("/")
    assert resp.status_code in (200, 404)
```

- [ ] **Step 3: Run backend tests (no regressions)**

Run: `cd formatter && python -m pytest -q`
Expected: PASS (segment/export/diarizer/prompt tests + updated page tests; the removed Jinja `/` test is replaced).

- [ ] **Step 4: Multi-stage Dockerfile** — replace `formatter/Dockerfile`:
```dockerfile
# Stage 1 — build the Vue SPA
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2 — Python app, with the built SPA copied in
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY --from=web /web/dist ./web/dist
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 5: Update `.dockerignore`** — ensure `formatter/.dockerignore` excludes web build cruft (append):
```
web/node_modules/
web/dist/
```

- [ ] **Step 6: Verify compose still builds config**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/app/main.py formatter/tests/test_pages.py formatter/Dockerfile formatter/.dockerignore
git commit -m "feat(formatter): serve Vue SPA from FastAPI + multi-stage Docker build"
```

- [ ] **Step 8: Manual end-to-end smoke (user-run, needs Ollama + diarizer + a model)**

```bash
docker compose up -d --build formatter    # builds the SPA + backend image
# ensure Ollama + `cd diarizer && ./run.sh` are running, model pulled
open http://localhost:8084                 # upload audio, format, export
```

---

## Self-Review

- **Spec coverage:** upload→diarize (Task 5 `onUpload` + api.diarize) ✓; TipTap WYSIWYG with speaker + italics (Task 5 TurnEditor) ✓; format via profile streaming (api.formatSegments + onFormat) ✓; SRT/VTT/TXT/MD export/download (Task 5 onExport) ✓; Vue+Vite+TS+Tailwind+shadcn-vue conventions (Task 1) ✓; SPA served by FastAPI + Docker (Task 6) ✓. Profile CRUD intentionally stays on the v1 `/manage` page (linked from the SPA).
- **Placeholder scan:** none — every step has complete code/config and a command with expected result. UI tasks are honestly gated by build + manual smoke.
- **Type consistency:** `Turn`/`Segment` are one shape across `turns.ts`, `api.ts`, `TurnEditor`, and `App.vue`, and match B1's `{start,end,speaker,text}`. `api.formatSegments` yields `Turn`; `groupTurns` returns `Turn[]`; both flow into `turns` state and back out as `segments` payloads. Markdown is the consistent wire format, bridged to TipTap HTML only inside `TurnEditor`.
