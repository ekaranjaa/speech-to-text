# Speech-to-Text Stack — Design

**Date:** 2026-06-11
**Location:** `~/Code/speech-to-text`
**Status:** Approved for planning

## Goal

Stand up a self-hosted **speech-to-text** stack that mirrors the structure and
aesthetic of the existing `~/Code/text-to-speech` setup (a hand-written,
well-commented `docker-compose.yml`). Primary use case: **transcribe audio/video
files** (meetings, podcasts, lectures) into transcripts and subtitles, with a
browser UI for managing a library of transcriptions and exporting subtitles.

## Reference: the TTS setup being mirrored

The TTS project is a 2-part Compose stack:

- **Kokoro-FastAPI** — the engine, OpenAI-compatible API.
- **OpenReader** — the UI / orchestrator that consumes the engine.

Conventions to preserve: a single hand-written `docker-compose.yml` with inline
explanatory comments, `restart: unless-stopped`, persistent storage, a CPU
profile, and host ports that do not collide with the TTS stack
(TTS uses `3003`, `8333`, `8880`).

## Chosen approach: Whishper (full transcription suite)

[Whishper](https://github.com/pluja/whishper) is an actively maintained,
local-first transcription + subtitling suite with a complete web UI. Decisive
fact: **Whishper's transcription engine is `faster-whisper`** (its
`transcription-api` service), so this satisfies the stated interest in
faster-whisper while delivering the richest file-transcription UI.

`speaches` (a different packaging of the same faster-whisper core that exposes a
clean OpenAI `/v1/audio/transcriptions` endpoint) is intentionally **out of
scope** — it serves the "scripting against an API" use case, not the
"file transcription with a UI" use case chosen here. It can be added later as a
separate service if API access is ever wanted. (YAGNI.)

### Approaches considered

1. **speaches + light UI** — closest to the exact named tooling, but a weaker
   library/editor experience. Rejected: user prioritized the richest file UI.
2. **Whishper (chosen)** — full suite; faster-whisper internally; heavier
   (6 services) but purpose-built for file transcription.
3. **Hybrid (speaches + a separate rich UI)** — most containers/maintenance for
   no benefit over option 2 here. Rejected: YAGNI.

## Target environment

- **Host:** Apple M1 Pro (arm64), macOS (Darwin 25.x), Docker 29 + Compose v5.
- **Implications:**
  - **CPU-only.** No NVIDIA GPU passthrough in Docker on macOS. Use Whishper's
    CPU profile / CPU transcription-api image.
  - **FerretDB instead of MongoDB.** MongoDB 5+ requires AVX, which is
    unreliable under Docker on Apple Silicon. Whishper officially supports
    FerretDB (PostgreSQL-backed, Mongo-compatible API) for exactly this case.

## Architecture

Six containers, orchestrated by a single hand-written `docker-compose.yml`,
unified behind an nginx reverse proxy so the user visits **one** URL.

| Service | Role | Notes |
|---|---|---|
| `transcription-api` | **faster-whisper** inference (CPU image) | the engine; downloads models on first use |
| `whishper-backend` | Go/Fiber API orchestrator | async job queue, WebSocket updates |
| `whishper-frontend` | SvelteKit web UI | drag-drop library, in-browser subtitle editor |
| `nginx` | reverse proxy / single entry point | exposed on host port **8083** |
| `ferretdb` | metadata store (Mongo-compatible) | ARM-safe replacement for MongoDB |
| `libretranslate` | subtitle translation, 60+ languages | **included** per user choice |

### Data flow

1. User uploads media (or pastes a URL) in the web UI at `http://localhost:8083`.
2. Backend persists the job to FerretDB and queues it.
3. `transcription-api` (faster-whisper) transcribes using the configured model.
4. Results stored in FerretDB + media/transcripts on a bind mount.
5. UI displays the transcript with an editor; optional translation via
   `libretranslate`.
6. User exports subtitles (SRT / VTT / JSON / TXT) — generated client-side.

## Configuration decisions

- **Default model:** `medium` — better accuracy than `small`, acceptable speed
  on M1 Pro CPU. User-changeable per transcription / via env.
- **Translation:** LibreTranslate **included**. Accept slower first boot while
  language models download.
- **UI host port:** **8083** (clear of TTS `3003/8333/8880` and Whishper's
  internal ports).
- **Persistence:** a `./whishper_data/` **bind mount** in the project folder
  (transcriptions, processed media, FerretDB data, downloaded whisper models) —
  mirrors how OpenReader persists its docstore, and keeps data visible/portable
  in the repo directory.
- **Restart policy:** `restart: unless-stopped` on all services (matches TTS).

## Deliverables

1. `~/Code/speech-to-text/docker-compose.yml` — hand-written, **commented** in
   the style of the TTS file, CPU profile, FerretDB backend, port 8083,
   bind-mount persistence, LibreTranslate included.
2. `~/Code/speech-to-text/.env` — configuration (public host/port, default
   model, data path, translation settings) with comments.
3. `~/Code/speech-to-text/.gitignore` — ignore `whishper_data/` and other
   runtime/local artifacts.
4. `~/Code/speech-to-text/README.md` — what it is, how to start/stop, where data
   lives, how to change the model, how to add `speaches` later for API access,
   and the M1/CPU/FerretDB rationale.

## Implementation notes / open items for the plan

- **Source of truth for the compose:** the **canonical upstream Whishper compose
  + `.env`** (current version) is the basis. The implementation's first step is
  to obtain the current official Whishper CPU compose and `.env.example` and
  adapt them — exact image tags and env var keys come from upstream, not from
  memory, to avoid drift.
- **Adaptations to apply to upstream:** select FerretDB backend; CPU
  transcription-api image; default model `medium`; host port 8083; bind-mount to
  `./whishper_data`; keep LibreTranslate; preserve `restart: unless-stopped`;
  add explanatory comments matching the TTS file's tone.
- **Verification:** `docker compose up -d` brings all six services healthy;
  the UI loads at `http://localhost:8083`; a short sample audio file transcribes
  end-to-end and exports an SRT. Document any first-run model-download wait.

## Out of scope

- Live/real-time dictation (system-wide voice typing).
- A standalone OpenAI-compatible API (`speaches`) — noted as a future add-on.
- GPU acceleration (not available on this host under Docker).
