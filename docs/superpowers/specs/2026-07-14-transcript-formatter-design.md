# Transcript Formatter — Design Spec

- **Date:** 2026-07-14
- **Status:** Approved (design), pending implementation plan
- **Repo:** `speech-to-text` (`main` branch)

## 1. Overview

Add a **local LLM post-processing stage** that reshapes a raw Whishper transcript
into a chosen writing style (e.g. GoTranscript "clean verbatim"). Whishper does
the acoustic work (audio → raw transcript); this new stage does the *text → text*
work of applying a style guide.

It ships as a **small self-hosted web app** (`formatter`) in the existing Docker
Compose stack. The user pastes or uploads a transcript, picks a **saved, editable
style profile**, and gets formatted text back to copy or download. The LLM runs
via **Ollama on the host** (native, for Metal GPU acceleration).

### Goals
- Reflow plain-text transcripts according to a saved style profile.
- Profiles are a named, editable library persisted to disk, seeded with two
  GoTranscript-derived profiles: **Full Verbatim** and **Clean Verbatim**.
- Fully local: no data leaves the machine, no per-use cost.
- Fit the existing repo conventions (Compose service, `.env`, git-ignored data dir).

### Non-goals (YAGNI — noted as possible future work)
- Timestamps in output, speaker labels, or diarization.
- Cloud/hosted models.
- Auth, multi-user, or job history/persistence of transcripts.
- Integrating into the Whishper UI itself (Whishper is unchanged).

## 2. Architecture

```
Browser ──HTTP──► formatter (Docker, FastAPI :8084)
                      │  profile CRUD → ./formatter_data/profiles/*.json
                      │
                      └──HTTP──► Ollama (host, native, :11434)  ── Metal GPU
```

- **`formatter`** — a small FastAPI + uvicorn app in a new container, published to
  the host at **http://localhost:8084** (8083 is Whishper). Conventions match the
  rest of the stack: `restart: unless-stopped`, `env_file: .env`, data under a
  git-ignored `./formatter_data/`.
- **Ollama stays native on the host.** Docker on macOS has no GPU passthrough
  (the repo already documents this for transcription), so a containerized model
  would be CPU-only and slow. The container reaches Ollama at
  `http://host.docker.internal:11434`, enabled by
  `extra_hosts: ["host.docker.internal:host-gateway"]` for portability.
- **Profiles persist as JSON files** under `./formatter_data/profiles/`, one file
  per profile, seeded on first boot.

### Why not run everything "in" Ollama
Ollama is a **model registry + inference runtime + HTTP API server** — not an app
platform. It has no web UI and does not manage profiles, chunk transcripts, or
handle uploads. The `formatter` app owns all of that and calls Ollama only for the
LLM step. Whisper transcription is unrelated to Ollama (Ollama runs text LLMs, not
speech-to-text) and remains Whishper's job.

## 3. Components

Each is a focused unit with a clear interface, independently testable.

### 3.1 Profile store (`app/profiles.py`)
CRUD over JSON files in the profiles dir. Seeds the two built-in profiles **only
when the profiles directory contains no files**, so user edits and deletions
persist across restarts (we never clobber an existing library).

Profile schema:
```json
{
  "id": "clean-verbatim",
  "name": "Clean Verbatim",
  "description": "GoTranscript-style clean verbatim: removes fillers, false starts, stutters.",
  "instructions": "…system prompt (the style rules)…",
  "model": null,
  "temperature": null
}
```
- `id` — slug, also the filename (`<id>.json`).
- `model` / `temperature` — optional per-profile overrides; fall back to the
  global env defaults when `null`.

Interface: `list()`, `get(id)`, `create(data)`, `update(id, data)`, `delete(id)`,
`seed_if_empty()`.

### 3.2 Chunking (`app/chunking.py`)
Long transcripts are split so each request fits comfortably in the model's context
and stays fast. Split on paragraph then sentence boundaries; never mid-sentence.
Default target `FORMATTER_MAX_CHUNK_WORDS` (~800 words). A single sentence longer
than the limit is passed whole. **No overlap** in v1 (avoids duplicated text on
reflow); rare boundary artifacts are an accepted limitation.

Interface: `split(text, max_words) -> list[str]`.

### 3.3 Ollama client (`app/ollama_client.py`)
Thin wrapper over Ollama's `/api/chat` using `httpx`. Streams tokens. Distinguishes
"Ollama unreachable" from "model not found" so the app can give the right hint.
Mockable so the formatting engine is testable without a live model.

Interface: `chat(model, system, user, temperature, stream=True)`,
`health() -> {reachable, models}`.

### 3.4 Formatting engine (`app/formatting.py`)
Orchestration: given `text` + a resolved profile, chunk the text, send each chunk
with the profile's `instructions` as the system prompt, stream results, and join
chunks with a blank line. Temperature defaults low (~0.2) for faithful reformatting.

Interface: `format_transcript(text, profile) -> stream[str]`.

### 3.5 Web UI (`app/templates`, `app/static`)
Two pages, plain server-rendered HTML + light vanilla JS (no build step):
- **Format** (`/`): a textarea (paste) + `.txt` file upload, a profile dropdown,
  a **Format** button, a streaming output area, and **Copy** / **Download .txt**.
- **Profiles** (`/manage`): list of profiles with create / edit / delete; an editor
  for name, description, instructions, and optional model/temperature overrides.

## 4. HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Format page |
| GET | `/manage` | Profiles management page |
| GET | `/api/health` | Ollama reachability + available models |
| GET | `/api/profiles` | List profiles |
| GET | `/api/profiles/{id}` | Get one profile |
| POST | `/api/profiles` | Create profile |
| PUT | `/api/profiles/{id}` | Update profile |
| DELETE | `/api/profiles/{id}` | Delete profile |
| POST | `/api/format` | `{text, profile_id, model?, temperature?}` → streamed formatted text |

`/api/format` streams the result (chunked response / SSE) so long transcripts show
progress instead of hanging.

## 5. Data flow

1. User pastes/uploads a transcript, selects a profile, clicks **Format**.
2. `POST /api/format` resolves the profile (applying model/temperature fallbacks).
3. Engine chunks the text, sends each chunk to Ollama with the profile's system
   prompt, streams tokens back.
4. UI renders streamed output; user copies or downloads `.txt`.

## 6. Seeded profiles (baked from GoTranscript guidelines)

Both are **reflow-only** subsets: they explicitly do **not** add speaker labels or
timestamps (out of scope for v1) and must **not invent** `[inaudible]` /
`[unintelligible]` markers, since the model has no audio.

### 6.1 Clean Verbatim — system prompt
> You are a professional transcript editor. You are given a raw, machine-generated
> transcript of spoken audio. Reformat it into GoTranscript-style **clean
> verbatim**. Never paraphrase, summarize, translate, reorder, or invent content —
> only reshape what is already present. Output only the edited transcript, with no
> preamble or commentary.
>
> **Remove:** filler words (uh, um, you know, like, I mean, so, well, kind of, sort
> of) when they add no meaning; false starts; stutters; and repetitions — except
> repetitions used for emphasis ("No, no, no."; "very, very happy").
>
> **Keep** interjections and expressions: Oh, Oh my God, Oh dear, Oh boy, et cetera.
> Do not remove "et cetera".
>
> **Convert:** yeah/yep/yup/mm-hmm → "yes" when they answer a question (otherwise
> drop bare acknowledgements to keep the text fluent); expand slang — gonna → going
> to, wanna → want to, gotta → got to, gotcha → got you, 'cause → because; alright →
> all right; ok/OK → Okay.
>
> **Keep spoken contractions exactly** (y'all, ain't, don't, it's). Do **not**
> correct grammatical errors. Do **not** use [sic]. Use correct spelling for
> misspoken words (e.g. "nitche" → "niche").
>
> **Punctuation & capitalization:** capitalize the first word of every sentence;
> end every sentence with a punctuation mark, except a sentence left incomplete,
> which ends with a double dash `--` (no spaces). Never use exclamation marks. Use
> `--` for incomplete/interrupted sentences. Use double quotation marks for direct
> quotations and internal dialogue; commas and periods go inside the quotes.
>
> **Numbers:** spell out zero–nine, use numerals for 10 and up; if a sentence mixes
> small and large numbers, use numerals for all. Money: $5, $1.5 million.
> Percentages: 100%. Years: '90s, 1990s. Times: 2:45 PM (capitalize AM/PM).
>
> **Abbreviations/acronyms:** no periods (USA, PhD); research correct capitalization
> (iPhone, UCLA, SaaS).
>
> **Non-verbal sounds:** only when clearly indicated in the source text, use
> lowercase bracket tags such as [laughs], [coughs], [crosstalk]. Never use
> parentheses for these. Do **not** invent [inaudible]/[unintelligible] tags or any
> timestamps — you have no audio. Preserve any bracketed tags already in the input.
>
> **Paragraphing:** break long stretches into short paragraphs (~100 words max),
> dividing where the meaning is clearest — often where the speaker links thoughts
> with "and", "so", or "but" — and drop those leading conjunctions when unnecessary.
>
> Do **not** add speaker labels or timestamps.

### 6.2 Full Verbatim — system prompt
> You are a professional transcript editor. You are given a raw, machine-generated
> transcript of spoken audio. Reformat it into GoTranscript-style **full verbatim**.
> Transcribe **everything as spoken** — never paraphrase, summarize, translate,
> reorder, or invent content. Output only the edited transcript, with no preamble
> or commentary.
>
> **Keep everything:** all filler words (um, uh, you know, kind of, sort of, I
> mean); false starts; stutters; repetitions; and slang written as spoken (kinda,
> gotta, wanna, dunno, gonna, 'cause). Keep affirmative/negative forms exactly
> (Mm-hmm, Uh-huh / Mm-mm, Uh-uh). Do not expand slang or remove anything.
>
> **Notation:** use a single dash `-` (no spaces) for stutters ("m-m-moist") and
> repetitions ("why is this- why is this moist"). Use a double dash `--` (no spaces)
> for false starts and speech errors ("I went on Tu-Thursday-- no, Friday.") and for
> incomplete/interrupted sentences.
>
> **Keep spoken contractions exactly.** Do **not** correct grammatical errors. Do
> **not** use [sic]. Use correct spelling for misspoken words.
>
> **Punctuation & capitalization, numbers, abbreviations, and quotations:** same
> rules as clean verbatim (capitalize sentence starts; end sentences with
> punctuation except a trailing `--`; never use exclamation marks; spell out
> zero–nine and use numerals for 10+; no periods in acronyms; double quotes for
> direct/internal dialogue).
>
> **Non-verbal sounds:** only when clearly indicated in the source text, use
> lowercase bracket tags (e.g. [laughs], [coughs], [crosstalk]); never parentheses.
> Do **not** invent [inaudible]/[unintelligible] tags or timestamps — you have no
> audio. Preserve bracketed tags already present.
>
> **Paragraphing:** break long speeches into short paragraphs (~100 words max) for
> readability, without changing any words.
>
> Do **not** add speaker labels or timestamps.

## 7. Configuration

Added to `.env` and `.env.example`:

| Variable | Meaning | Default |
|---|---|---|
| `FORMATTER_PORT` | host port for the UI | `8084` |
| `OLLAMA_HOST` | Ollama API base URL (host) | `http://host.docker.internal:11434` |
| `FORMATTER_MODEL` | default Ollama model | `qwen2.5:7b-instruct` |
| `FORMATTER_TEMPERATURE` | default sampling temperature | `0.2` |
| `FORMATTER_MAX_CHUNK_WORDS` | max words per chunk | `800` |

Model rationale: on a 16 GB M1 Pro with the Docker stack resident, a 7B model
(~4.7 GB) is the comfortable default; bump `FORMATTER_MODEL=qwen2.5:14b` when not
transcribing simultaneously.

## 8. Error handling

- **Ollama unreachable** → 503 with: "Ollama isn't reachable at `$OLLAMA_HOST`.
  Start it (open the Ollama app or run `ollama serve`)."
- **Model not pulled** → actionable hint: "Model `qwen2.5:7b-instruct` isn't
  installed. Run: `ollama pull qwen2.5:7b-instruct`." (Mirrors the README's
  Whishper first-run note.)
- **Empty input** → 400 with a clear message.
- **Very large input** → still processed via chunking; the UI notes it may take a
  while and shows streaming progress.
- **Profile not found / invalid profile JSON** → 404 / 400 with the offending id.

## 9. Testing

Unit tests with a **mocked Ollama client** (no live model needed):
- `test_chunking.py` — boundary splitting, tiny input, input far over the limit, a
  single oversized sentence, paragraph preservation.
- `test_profiles.py` — CRUD round-trips; `seed_if_empty` seeds exactly the two
  profiles on an empty dir and is a no-op when files exist.
- `test_formatting.py` — chunk → format → join with a fake client (e.g. echo), plus
  error mapping (unreachable vs. model-not-found).

Manual end-to-end: run a real Whishper `.txt` export through both seeded profiles
and eyeball against the GoTranscript rules.

## 10. File layout

```
formatter/
  Dockerfile
  requirements.txt          # fastapi, uvicorn, httpx, jinja2, python-multipart, pytest
  app/
    __init__.py
    main.py                 # FastAPI app + routes
    config.py               # env parsing
    profiles.py             # profile store (CRUD + seeding)
    seed_profiles.py        # the two baked-in profiles
    chunking.py             # transcript chunking
    ollama_client.py        # Ollama HTTP wrapper (mockable)
    formatting.py           # orchestration
    templates/format.html
    templates/profiles.html
    static/app.js
    static/style.css
  tests/
    test_chunking.py
    test_profiles.py
    test_formatting.py
formatter_data/             # git-ignored; profiles/*.json
```

### Compose service (added to `docker-compose.yml`)
```yaml
  formatter:
    build: ./formatter
    container_name: whishper-formatter
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - ${FORMATTER_PORT:-8084}:8000
    volumes:
      - ./formatter_data/profiles:/app/profiles
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      OLLAMA_HOST: ${OLLAMA_HOST:-http://host.docker.internal:11434}
      FORMATTER_MODEL: ${FORMATTER_MODEL:-qwen2.5:7b-instruct}
      FORMATTER_TEMPERATURE: ${FORMATTER_TEMPERATURE:-0.2}
      FORMATTER_MAX_CHUNK_WORDS: ${FORMATTER_MAX_CHUNK_WORDS:-800}
```

## 11. One-time setup

1. `ollama pull qwen2.5:7b-instruct`
2. Add the `formatter` service + env vars (above); add `formatter_data/` to
   `.gitignore`.
3. `docker compose up -d --build`
4. Open **http://localhost:8084**.
5. Update `README.md` with a "Formatter" section (stack table, port, Ollama
   prerequisite, first-run note).

## 12. Future work (out of scope now)
- Timestamp emission (every ~2 min) and speaker labels, once we accept
  `.srt`/`.vtt`/`.json` input with timing.
- Optional cloud model routing for top quality.
- Cross-chunk style consistency (carry a short style memo between chunks).
