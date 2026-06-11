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

**Corrected during planning from the real upstream compose:** Whishper deploys as
**three containers**, not six. The `pluja/whishper` image is an all-in-one app
that bundles the SvelteKit frontend, the Go backend, the `faster-whisper`
transcription service, and nginx internally. The compose only orchestrates:

| Service | Image | Role | Notes |
|---|---|---|---|
| `whishper` | `pluja/whishper:latest` | all-in-one app (UI + backend + **faster-whisper** + nginx) | only service published to host, on port **8083** (`8083:80`) |
| `mongo` | `mongo:7` | metadata store | internal only (`expose`, not published); arm64 image |
| `translate` | `libretranslate/libretranslate:latest` | subtitle translation, 60+ languages | **included** per user choice; internal only |

### Database: mongo, not FerretDB (corrected)

The approved spec called for FerretDB on the assumption that MongoDB's AVX
requirement breaks on Apple Silicon. That assumption was wrong: **AVX is an
x86-only concern and does not apply to a natively-run arm64 MongoDB image.**
`mongo:7` publishes an arm64 build and runs natively on the M1 Pro. The upstream
compose uses plain `mongo`, so we stay aligned with it (pinned to `mongo:7` for
reproducibility) and document FerretDB only as a fallback if mongo misbehaves.

### Data flow

1. User uploads media (or pastes a URL) in the web UI at `http://localhost:8083`.
2. The `whishper` app persists the job to `mongo` and queues it.
3. The bundled `faster-whisper` service transcribes using the selected model.
4. Results stored in `mongo` + media/transcripts on a bind mount.
5. UI displays the transcript with an editor; optional translation via
   `translate` (LibreTranslate).
6. User exports subtitles (SRT / VTT / JSON / TXT) — generated client-side.

## Configuration decisions

- **Models preloaded:** `WHISPER_MODELS=small,medium` in `.env` (upstream default
  is `tiny,small`). `medium` is the intended default for accuracy on M1 Pro CPU;
  `small` is kept for quick tests. Both download on first container start and the
  user picks per transcription in the UI.
- **Persist models (new vs upstream):** add a `./whishper_data/models:/app/models`
  bind mount. Upstream maps no volume for `WHISPER_MODELS_DIR=/app/models`, so
  multi-GB models re-download on every container *recreate*; the mount fixes that.
- **CPU threads:** `CPU_THREADS=8` (upstream default 4) to use the M1 Pro better,
  echoing the TTS file's `ONNX_NUM_THREADS=8`.
- **Translation:** LibreTranslate **included** (`LT_LOAD_ONLY=es,en,fr`,
  user-editable). Accept slower first boot while language models download.
- **UI host port:** **8083** (`8083:80`), clear of TTS `3003/8333/8880`.
  `WHISHPER_HOST` in `.env` must match: `http://127.0.0.1:8083`.
- **Persistence:** a `./whishper_data/` **bind mount** tree in the project folder
  (`mongo` db, uploads, logs, libretranslate data/cache, whisper models) —
  mirrors how OpenReader persists its docstore.
- **Restart policy:** `restart: unless-stopped` on all services (matches TTS).
- **Cleanups vs upstream:** drop the obsolete `version: "3.9"` key; pin `mongo:7`
  (upstream uses bare `mongo`); add explanatory comments in the TTS file's tone.
  `mongo` and `translate` stay `expose`-only (not published to host).

## Deliverables

1. `~/Code/speech-to-text/docker-compose.yml` — hand-written, **commented** in
   the style of the TTS file: 3 services, CPU profile, `mongo:7`, port 8083,
   `./whishper_data` bind mounts incl. a `models` mount, LibreTranslate included.
2. `~/Code/speech-to-text/.env` — adapted from upstream `example.env`
   (`WHISPER_MODELS=small,medium`, `WHISHPER_HOST=http://127.0.0.1:8083`,
   `LT_LOAD_ONLY`, DB creds, `CPU_THREADS=8`) with comments.
3. `~/Code/speech-to-text/.gitignore` — ignore `whishper_data/` (runtime data).
4. `~/Code/speech-to-text/README.md` — what it is, start/stop, where data lives,
   how to change the model, first-run model-download wait, how to add `speaches`
   later for API access, and the M1 Pro / CPU / arm64-mongo rationale.

## Implementation notes (resolved during planning)

The canonical upstream files have already been fetched and pinned as the basis:
- compose: `https://raw.githubusercontent.com/pluja/whishper/main/docker-compose.yml`
- env: `https://raw.githubusercontent.com/pluja/whishper/main/example.env`

**Adaptations to apply to upstream:** keep `mongo` (pin `mongo:7`); CPU profile
(`PUBLIC_WHISHPER_PROFILE: cpu`, already in upstream cpu compose); change host
port `8082`→`8083` and matching `WHISHPER_HOST`; add `./whishper_data/models`
bind mount; `WHISPER_MODELS=small,medium`; `CPU_THREADS=8`; keep LibreTranslate;
preserve `restart: unless-stopped`; drop `version:` key; add explanatory comments.

**Verification:** `docker compose config` resolves; `docker compose up -d` brings
all three services up (mongo + translate healthy, whishper reachable); the UI
loads at `http://localhost:8083`; a short sample audio file transcribes
end-to-end and exports an SRT. Document the first-run model-download wait.

## Out of scope

- Live/real-time dictation (system-wide voice typing).
- A standalone OpenAI-compatible API (`speaches`) — noted as a future add-on.
- GPU acceleration (not available on this host under Docker).
