# Speaker-Aware Transcript Studio — Design (v2)

**Date:** 2026-07-15
**Status:** Approved (design), pending per-subsystem specs
**Supersedes/extends:** `2026-07-14-transcript-formatter-design.md` (the plain-text
reflow formatter). That work is not discarded — its FastAPI backend, Ollama client,
profile store, chunker, and streaming become the backbone of Subsystem B below.

## Goal

Turn the transcript formatter from a plain-text reflow box into a **local,
speaker-aware transcription studio**: diarize audio into speaker-labeled,
timestamped segments, reflow each speaker's turn into a saved GoTranscript-style
profile via a local LLM, refine it in a WYSIWYG editor, and export SRT / VTT /
TXT / Markdown. Everything runs locally.

## Motivation (four concerns raised against v1)

1. **Frontend language.** v1's UI is Jinja2 + vanilla JS. The maintainer is more
   fluent in TypeScript and wants the UI in TS.
2. **WYSIWYG editing.** v1 outputs read-only plain text. A rich editor is needed
   to refine the formatted result.
3. **Missing GoTranscript rules.** v1's prompts miss rules such as *italicizing
   titles* (films, books, plays) and *not quoting unintelligible speech*.
4. **Speakers + subtitle formats.** v1 was deliberately text-only. GoTranscript
   requires speaker labels (Speaker 1 / Interviewer / real names), which belong in
   timestamped SRT/VTT output — reopening the text-only constraint.

## Key technical reality that shapes the design

Whishper / faster-whisper **transcribe but do not identify speakers.** Diarization
("who spoke when") is a separate model — **pyannote** — normally combined with the
ASR output. There is no single model that does both; every diarized transcript is
an ASR model plus a speaker model, merged. This is why speakers require new
infrastructure (Subsystem A).

## Architecture overview

Two subsystems, built in sequence (A defines B's input contract, so A first):

```
             ┌─────────────────────── Subsystem A (host-native, Python) ───────────────────────┐
  audio  ──▶ │ faster-whisper (word-level timestamps)  +  pyannote (speaker turns)  → merge     │
             └───────────────────────────────────────┬─────────────────────────────────────────┘
                                                      │  segments JSON: [{start,end,speaker,text}]
                                                      ▼
             ┌─────────────────────── Subsystem B (Vue frontend + Python API in Docker) ────────┐
             │  load segments → pick style profile → LLM reflow per speaker turn (streaming)     │
             │  → refine in TipTap WYSIWYG (rename speakers, edit text, italics)                 │
             │  → export SRT / VTT / TXT / Markdown                                              │
             └──────────────────────────────────────────────────────────────────────────────────┘
```

Each subsystem gets its own spec → plan → implementation cycle.

## Decision log

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Speaker source | Add diarization upstream | Only way to get real speaker IDs; LLM cannot invent identities from text |
| 2 | Diarizer shape | Self-contained: audio → faster-whisper + pyannote in one pass | Slimmest per-job path; no double transcription, no transcript shuttling; word-level timestamps |
| 3 | Diarizer runtime | Host-native, like Ollama | Wants Metal/MPS; Docker on macOS is CPU-only; avoids a multi-GB image; consistent with the existing Ollama pattern |
| 4 | B backend | Keep the existing Python FastAPI API | Already built + tested; the diarizer is Python anyway, so the backend language stays consistent |
| 5 | B frontend | Vue 3 + Vite + TypeScript, Tailwind, shadcn-vue | Maintainer's preferred stack |
| 6 | Editor | TipTap (`@tiptap/vue-3`) | ProseMirror structured document maps 1:1 to the segment model; Vue-native; supports italic marks |
| 7 | Timestamps in editor | Preserved, not hand-editable | Need is relabel + restyle, not re-timing; Whishper already does subtitle timing |
| 8 | pyannote token | HuggingFace token required (documented prerequisite) | pyannote models are gated; inference still 100% local |
| 9 | Exports | SRT + VTT + TXT + Markdown (all four) | Cover subtitle + plain + rich needs |
| 10 | Persistence in B | Profiles persist; transcripts do not | Keep B slim; Whishper remains the library for non-speaker work |

## Subsystem A — Diarizer service

**Responsibility:** given an audio file, produce a speaker-labeled, timestamped
transcript. Nothing else.

- **Runtime:** a **host-native** Python HTTP service (not Docker), mirroring how
  Ollama runs, so it can use the Metal GPU (MPS) and stay out of a heavy container.
- **Pipeline:**
  1. faster-whisper transcribes with `word_timestamps=True`.
  2. pyannote (`pyannote/speaker-diarization-3.1`) produces speaker turn segments.
  3. Merge: each word is assigned to the speaker whose diarization segment
     overlaps the word's midpoint; consecutive same-speaker words are grouped into
     segments.
- **Output (the A→B contract):**
  ```json
  {
    "segments": [
      { "start": 0.00, "end": 4.20, "speaker": "SPEAKER_00", "text": "..." },
      { "start": 4.20, "end": 9.85, "speaker": "SPEAKER_01", "text": "..." }
    ],
    "speakers": ["SPEAKER_00", "SPEAKER_01"],
    "language": "en"
  }
  ```
  Labels are generic (`SPEAKER_00`); the user renames them in B.
- **HTTP surface (minimum):**
  - `GET /health` → `{ "ready": true, "device": "mps|cpu", "model": "medium" }`
  - `POST /diarize` (multipart: `audio`, optional `num_speakers`) → segments JSON.
- **Model cache:** point faster-whisper at the existing `./whishper_data/models`
  CT2 cache so whisper weights are not stored twice.
- **HuggingFace token:** read from the diarizer's own environment (`HF_TOKEN`).
  Because the diarizer is host-native, this lives in the diarizer's local `.env`
  (e.g. `diarizer/.env`), **not** the Docker compose `.env`. Setup docs will
  prompt for it, and the service must fail clearly ("set HF_TOKEN and accept the
  pyannote model terms") when it is missing — the same clear-failure ethos as
  Whishper's first-run and the formatter's "model not pulled" message.
- **Config (host-native `.env`):** `DIARIZER_PORT` (default 8090), `HF_TOKEN`,
  `DIARIZER_WHISPER_MODEL` (default `medium`), `DIARIZER_DEVICE` (default `auto` →
  mps if available else cpu), `DIARIZER_MODEL_CACHE` (default `./whishper_data/models`).

## Subsystem B — Formatter/editor

**Responsibility:** given segments (from A), reflow them into a style profile, let
the user refine, and export.

- **Frontend:** Vue 3 + Vite + TypeScript, Tailwind, **shadcn-vue** (reka-ui/Radix
  Vue components), **TipTap** WYSIWYG.
  - Editor document = a list of **speaker-turn blocks**: each block has an editable
    **speaker label** and **rich text** (bold/italic marks). Italic is used for
    titles per GoTranscript.
  - Timestamps (`start`/`end`) are carried on each block as invisible metadata and
    surfaced only at export time.
  - The Vite build is served as static assets by the FastAPI backend (single B
    container); in dev, the Vite dev server proxies `/api` to FastAPI.
- **Backend (extends v1 FastAPI):**
  - Keeps: Ollama client, profile store, streaming, health checks, config.
  - Adds: **segment-aware formatting.** The LLM reflows the `text` of each speaker
    turn (or a run of consecutive same-speaker turns packed under the word budget)
    while `{speaker, start, end}` pass through untouched. Chunking never merges two
    different speakers into one chunk.
  - Adds: a thin proxy to the host diarizer (`POST /api/diarize` → forwards
    multipart audio to `DIARIZER_HOST`, same `host.docker.internal` bridge already
    used for Ollama) plus preflight health checks that return clean HTTP errors
    when the diarizer is unreachable or its token/model is missing.
  - Adds: **export renderers** (below).
- **Formatting flow:** upload audio → `POST /api/diarize` → segments load into the
  editor → choose profile → `POST /api/format` streams reflowed turns back → user
  edits → export.
- **Profiles:** the seeded **Full Verbatim** and **Clean Verbatim** profiles are
  retained and upgraded (see Concern #3). Profiles remain editable and persist
  under the existing profiles volume.

## A → B interface

The segments JSON above is the single contract. B treats it as the source of
truth: the editor is a view over `segments`, formatting rewrites `text` per
segment, and exports render `segments` (post-edit) into each format. This keeps A
swappable (a future WhisperX or word-level upgrade changes A only).

## Export renderers (all four)

| Format | Speakers | Timestamps | Italics |
|--------|----------|------------|---------|
| **SRT** | `Name: text` prefix in cue | cue timing from `start`/`end` | `<i>…</i>` |
| **VTT** | native `<v Speaker>text</v>` voice tags | cue timing | `<i>…</i>` |
| **TXT** | `Speaker: text` paragraphs | omitted | dropped (plain) |
| **Markdown** | `**Speaker:**` label | omitted | `*…*` |

Plus "copy rich" (HTML) from the editor for pasting into a word processor with
real italics.

## Concern #3 — GoTranscript rule upgrades (B's prompts)

When B's spec is written, re-audit the full
[GoTranscript guidelines](https://gotranscript.com/transcription-guidelines) and
expand the seeded prompts to cover the gaps, at minimum:

- **Italicize titles** of films, books, plays, albums, TV shows, etc. The LLM
  emits Markdown emphasis (`*Title*`); TipTap renders it as an italic mark; export
  renderers map it to `<i>` (SRT/VTT) or `*…*` (Markdown).
- **Do not put quotation marks around unintelligible or uncertain speech.**
- Keep v1's existing rules (numbers, contractions, non-verbal bracket tags,
  paragraphing, no invented `[inaudible]`/timestamps) and make them speaker-aware.

Prompts also gain speaker context: the model is told it is reformatting a single
speaker's turn and must not merge, reorder, or reattribute across speakers.

## What is reused vs. new

- **Reused (from v1, on `feature/transcript-formatter`):** FastAPI app factory,
  `OllamaClient`, `ProfileStore` + seed profiles, `split_transcript` chunker
  (generalized to respect segment/speaker boundaries), streaming `/api/format`,
  config loader, Docker service + compose wiring.
- **New:** the host-native diarizer service (A); the Vue/Vite/Tailwind/shadcn-vue/
  TipTap frontend (replaces Jinja + vanilla JS); segment-aware formatting +
  chunking; the `/api/diarize` proxy; the four export renderers; upgraded prompts.

## Prerequisites (documented for the user)

1. **Ollama** running on the host with a pulled model (existing v1 requirement).
2. **HuggingFace token** in the diarizer's `.env`, with the pyannote model terms
   accepted (one-time; inference stays local).
3. Python environment on the host for the diarizer (torch + faster-whisper +
   pyannote), analogous to installing Ollama.

## Sequencing & branch handling

1. Spec + plan + build **Subsystem A** (diarizer) first — it produces B's input.
2. Spec + plan + build **Subsystem B** (formatter/editor v2) on top of the
   existing v1 backend.

The 11 commits on `feature/transcript-formatter` (v1) are the foundation for B.
Whether to merge v1 to `main` first or keep building on the branch is an
implementation-time decision, taken when we reach it.

## Out of scope (YAGNI for v1 of this design)

- Hand-editable timestamps / cue splitting in the editor (Whishper covers re-timing).
- A persistent transcript library inside B (Whishper is the library).
- Automatic pipeline triggering from Whishper completion.
- A Dockerized (CPU-only) diarizer variant — possible later / on the `gpu` branch.
- Overlapping-speech precision beyond midpoint assignment.

## Risks / notes

- **pyannote on MPS** has partial operator support; the service may fall back to
  CPU for some ops. Acceptable for an offline/batch step; `DIARIZER_DEVICE` allows
  forcing `cpu`.
- **First-run downloads** (whisper weights if not shared, pyannote model) are large
  and gated — must fail with a clear, actionable message.
- **Model-cache sharing** assumes the diarizer's faster-whisper and Whishper use
  compatible CT2 model layouts; verify during A's implementation, fall back to a
  separate cache if not.
