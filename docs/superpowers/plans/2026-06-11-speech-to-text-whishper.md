# Speech-to-Text (Whishper) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a self-hosted, file-transcription speech-to-text stack (Whishper, powered by faster-whisper) via a single hand-written Docker Compose, tuned for Apple Silicon (M1 Pro / arm64, CPU-only), mirroring the sibling `~/Code/text-to-speech` setup.

**Architecture:** Three containers orchestrated by `docker-compose.yml`: `whishper` (all-in-one app — SvelteKit UI + Go backend + faster-whisper + nginx, the only host-published service on port 8083), `mongo:7` (metadata, internal), and `translate` (LibreTranslate, internal). Config lives in `.env`. All runtime data persists under `./whishper_data/` (git-ignored).

**Tech Stack:** Docker Compose v2, `pluja/whishper`, `mongo:7`, `libretranslate`, faster-whisper (bundled).

**Spec:** `docs/superpowers/specs/2026-06-11-speech-to-text-whishper-design.md`

**Working directory:** `~/Code/speech-to-text` (already a git repo).

**Note on TDD:** This is infrastructure/config, not application code, so there are no unit tests. The equivalent of "the test" here is concrete verification: `docker compose config` for static validation and a live bring-up + end-to-end transcription for behavioral validation. Verification commands and expected output are given explicitly.

---

### Task 1: Author `docker-compose.yml`

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write the compose file**

Create `docker-compose.yml` with exactly this content:

```yaml
# Speech-to-Text — Whishper (faster-whisper) self-hosted transcription suite.
# CPU profile, tuned for Apple Silicon (M1 Pro / arm64). Mirrors the sibling
# text-to-speech compose: inline comments, restart: unless-stopped, persistent
# data under ./whishper_data. Visit the UI at http://localhost:8083.
#
# Adapted from the official upstream CPU compose:
#   https://github.com/pluja/whishper  (docker-compose.yml + example.env)

services:
  # MongoDB — stores transcription jobs and metadata. Internal only (not
  # published to the host). mongo:7 ships an arm64 image, so it runs natively
  # on Apple Silicon (the AVX requirement that breaks Mongo is x86-only).
  mongo:
    image: mongo:7
    container_name: whishper-mongo
    env_file:
      - .env
    restart: unless-stopped
    volumes:
      - ./whishper_data/db_data:/data/db
      - ./whishper_data/db_data/logs/:/var/log/mongodb/
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${DB_USER:-whishper}
      MONGO_INITDB_ROOT_PASSWORD: ${DB_PASS:-whishper}
    expose:
      - 27017
    command: ['--logpath', '/var/log/mongodb/mongod.log']

  # LibreTranslate — neural translation for subtitles (60+ languages). The set
  # of languages it loads is limited via LT_LOAD_ONLY in .env to keep first
  # boot fast. Internal only.
  translate:
    image: libretranslate/libretranslate:latest
    container_name: whishper-libretranslate
    restart: unless-stopped
    env_file:
      - .env
    tty: true
    environment:
      LT_DISABLE_WEB_UI: "True"
      LT_UPDATE_MODELS: "True"
    volumes:
      - ./whishper_data/libretranslate/data:/home/libretranslate/.local/share
      - ./whishper_data/libretranslate/cache:/home/libretranslate/.local/cache
    expose:
      - 5000
    networks:
      default:
        aliases:
          - translate
    healthcheck:
      test: ['CMD-SHELL', './venv/bin/python scripts/healthcheck.py']
      interval: 2s
      timeout: 3s
      retries: 5

  # Whishper — all-in-one app: web UI + Go backend + faster-whisper + nginx.
  # The only service published to the host. CPU transcription profile.
  whishper:
    image: pluja/whishper:${WHISHPER_VERSION:-latest}
    container_name: whishper
    pull_policy: always
    env_file:
      - .env
    restart: unless-stopped
    depends_on:
      - mongo
      - translate
    ports:
      - 8083:80
    volumes:
      - ./whishper_data/uploads:/app/uploads
      - ./whishper_data/logs:/var/log/whishper
      # Persist downloaded whisper models so they are not re-downloaded on every
      # container recreate (upstream omits this mount).
      - ./whishper_data/models:/app/models
    networks:
      default:
        aliases:
          - whishper
    environment:
      PUBLIC_INTERNAL_API_HOST: "http://127.0.0.1:80"
      PUBLIC_TRANSLATION_API_HOST: ""
      PUBLIC_API_HOST: ${WHISHPER_HOST:-}
      PUBLIC_WHISHPER_PROFILE: cpu
      WHISPER_MODELS_DIR: /app/models
      UPLOAD_DIR: /app/uploads
      CPU_THREADS: ${CPU_THREADS:-8}
```

- [ ] **Step 2: Validate the compose syntax (will warn about missing .env vars — that's expected here)**

Run: `cd ~/Code/speech-to-text && docker compose config >/dev/null && echo COMPOSE_OK`
Expected: prints `COMPOSE_OK`. (Compose may print warnings that `WHISHPER_HOST`/`CPU_THREADS` are unset — acceptable; `.env` is added in Task 2. Any *error* about YAML/structure must be fixed before continuing.)

- [ ] **Step 3: Commit**

```bash
cd ~/Code/speech-to-text
git add docker-compose.yml
git commit -m "Add Whishper docker-compose (CPU, arm64, port 8083)"
```

---

### Task 2: Author `.env`

**Files:**
- Create: `.env`

- [ ] **Step 1: Write the env file**

Create `.env` with exactly this content:

```bash
# ── Whishper speech-to-text configuration ───────────────────────────────────

# Languages LibreTranslate loads (fewer = faster first boot, less disk). See:
# https://github.com/LibreTranslate/LibreTranslate#configuration-parameters
LT_LOAD_ONLY=es,en,fr

# Whisper models to preload (downloaded on first start, persisted under
# ./whishper_data/models). 'medium' is the default for accuracy on M1 Pro CPU;
# 'small' is kept for quick tests. Options: tiny,base,small,medium,large-v3
WHISPER_MODELS=small,medium

# Public URL the browser uses to reach the app — MUST match the host port
# mapping in docker-compose.yml (8083:80).
WHISHPER_HOST=http://127.0.0.1:8083

# faster-whisper CPU threads. Upstream default is 4; bumped for the M1 Pro.
CPU_THREADS=8

# MongoDB credentials (internal only — mongo is not published to the host).
DB_USER=whishper
DB_PASS=whishper
```

- [ ] **Step 2: Validate vars now resolve with no warnings**

Run: `cd ~/Code/speech-to-text && docker compose config 2>&1 | grep -Ei 'warn|error' || echo NO_WARNINGS`
Expected: prints `NO_WARNINGS` (the `WHISHPER_HOST` / `CPU_THREADS` warnings from Task 1 are gone).

- [ ] **Step 3: Confirm the port mapping resolved to 8083**

Run: `cd ~/Code/speech-to-text && docker compose config | grep -E 'published:|target:' | head`
Expected: shows `published: "8083"` with `target: 80`.

- [ ] **Step 4: Commit**

```bash
cd ~/Code/speech-to-text
git add .env
git commit -m "Add Whishper .env (models small,medium; port 8083; 8 CPU threads)"
```

---

### Task 3: Author `.gitignore`

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Write the gitignore**

Create `.gitignore` with exactly this content:

```gitignore
# Runtime data: mongo db, uploads, logs, libretranslate, downloaded whisper
# models. Can be large (multi-GB) and is machine-local — never commit it.
whishper_data/

# macOS
.DS_Store
```

- [ ] **Step 2: Verify whishper_data is ignored**

Run: `cd ~/Code/speech-to-text && mkdir -p whishper_data && git check-ignore whishper_data && echo IGNORED`
Expected: prints `whishper_data` then `IGNORED`.

- [ ] **Step 3: Commit**

```bash
cd ~/Code/speech-to-text
git add .gitignore
git commit -m "Ignore whishper_data runtime directory"
```

---

### Task 4: Author `README.md`

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

Create `README.md` with exactly this content:

````markdown
# speech-to-text

Self-hosted **speech-to-text** for transcribing audio/video files (meetings,
podcasts, lectures) into transcripts and subtitles, with a browser UI for
managing a library and exporting SRT / VTT / JSON / TXT.

Powered by [**Whishper**](https://github.com/pluja/whishper), whose transcription
engine is [**faster-whisper**](https://github.com/SYSTRAN/faster-whisper). This
is the speech-to-text sibling of the `text-to-speech` (Kokoro + OpenReader)
setup, and it runs entirely locally.

## Stack

Three containers (see `docker-compose.yml`):

| Service | Role | Host-exposed? |
|---|---|---|
| `whishper` | all-in-one app: web UI + backend + **faster-whisper** + nginx | yes, **http://localhost:8083** |
| `mongo` | transcription metadata store | no (internal) |
| `translate` | LibreTranslate, subtitle translation (60+ languages) | no (internal) |

Tuned for **Apple Silicon (M1 Pro / arm64), CPU-only** — Docker on macOS has no
GPU passthrough. All three images publish native arm64 builds.

## Quick start

```bash
cd ~/Code/speech-to-text
docker compose up -d      # pulls images, starts the stack
```

Then open **http://localhost:8083**.

**First run downloads models and language data**, so the first transcription is
slow and the `translate` service takes a while to become healthy. Preloaded
whisper models are set by `WHISPER_MODELS` in `.env` (`small,medium`) and are
cached under `./whishper_data/models`, so this only happens once.

Transcribe by uploading a file (or pasting a URL) in the UI, picking a model
(`medium` recommended; `small` for quick tests), then exporting subtitles.

```bash
docker compose logs -f whishper   # follow app logs
docker compose ps                 # service status
docker compose down               # stop (data is kept under ./whishper_data)
```

## Configuration (`.env`)

| Variable | Meaning | Default |
|---|---|---|
| `WHISPER_MODELS` | models preloaded/available in the UI | `small,medium` |
| `WHISHPER_HOST` | public URL — must match the host port in compose | `http://127.0.0.1:8083` |
| `CPU_THREADS` | faster-whisper CPU threads | `8` |
| `LT_LOAD_ONLY` | LibreTranslate languages to load | `es,en,fr` |
| `DB_USER` / `DB_PASS` | mongo credentials (internal only) | `whishper` |

To change the UI port, edit **both** the `ports:` mapping in
`docker-compose.yml` (`8083:80`) and `WHISHPER_HOST` in `.env`, then
`docker compose up -d`.

## Data

Everything persists under `./whishper_data/` (git-ignored): `db_data/` (mongo),
`uploads/` (your media + transcripts), `models/` (downloaded whisper models),
`libretranslate/`, and `logs/`. Delete a subfolder to reset that piece; delete
the whole folder for a clean slate.

## Notes & troubleshooting

- **Why mongo and not FerretDB?** MongoDB's AVX requirement is x86-only and does
  not apply to a natively-run arm64 image, so `mongo:7` works fine on the M1 Pro.
  If mongo ever misbehaves on this host, Whishper documents a FerretDB backend as
  a fallback: https://whishper.net
- **Want a scriptable API instead of the UI?** Add
  [`speaches`](https://github.com/speaches-ai/speaches) — a different packaging
  of the same faster-whisper core that exposes an OpenAI-compatible
  `/v1/audio/transcriptions` endpoint — as an extra service. Out of scope here.
- **GPU:** not available under Docker on macOS; this stack is CPU-only by design.
````

- [ ] **Step 2: Sanity-check it renders (no broken fences)**

Run: `cd ~/Code/speech-to-text && grep -c '```' README.md`
Expected: an **even** number (all code fences are closed).

- [ ] **Step 3: Commit**

```bash
cd ~/Code/speech-to-text
git add README.md
git commit -m "Add README for the Whishper speech-to-text stack"
```

---

### Task 5: Live bring-up and end-to-end verification

This is the behavioral verification. It downloads images and models, so it can
take several minutes on first run. No code changes; do not commit anything here
(runtime data is git-ignored).

**Files:** none (operational)

- [ ] **Step 1: Pull and start the stack**

Run: `cd ~/Code/speech-to-text && docker compose up -d`
Expected: images pull, then `mongo`, `whishper-libretranslate`, and `whishper`
report `Started`/`Running`. (`translate` may sit in `health: starting` while it
downloads language models.)

- [ ] **Step 2: Confirm all three containers are running**

Run: `cd ~/Code/speech-to-text && docker compose ps`
Expected: three services listed; `whishper` and `mongo` `running`, `translate`
`running` (becomes `healthy` after its model download finishes).

- [ ] **Step 3: Confirm the web UI is reachable**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8083`
Expected: `200` (retry for a minute or two if the app is still starting —
`docker compose logs whishper` shows progress).

- [ ] **Step 4: End-to-end transcription (manual)**

In a browser at **http://localhost:8083**: create/upload a short audio clip
(e.g. a 10–30s voice memo), select the **medium** model, run the transcription,
and once it completes, export it as **SRT**.
Expected: a transcript appears in the library and a `.srt` file downloads with
timestamped cues. (First transcription includes a one-time model download if
`medium` wasn't already cached.)

- [ ] **Step 5: Record the result**

Note in your handoff: which models were preloaded, approximate time for the
sample transcription, and any first-run waits observed. If Step 3 or 4 failed,
capture `docker compose logs whishper` and stop for review rather than patching
blindly (use superpowers:systematic-debugging).

---

## Self-Review (completed by plan author)

- **Spec coverage:** All deliverables map to tasks — compose (T1), .env (T2),
  .gitignore (T3), README (T4), verification (T5). The model-persistence mount,
  port 8083, `WHISPER_MODELS=small,medium`, `CPU_THREADS=8`, mongo:7, and
  LibreTranslate-included decisions are all reflected in T1/T2.
- **Placeholders:** none — every file's full content is inline; every step has an
  exact command and expected output.
- **Consistency:** `8083`, `WHISHPER_HOST=http://127.0.0.1:8083`,
  `WHISPER_MODELS=small,medium`, and `CPU_THREADS=8` match across compose, .env,
  and README. Volume paths under `./whishper_data/` are consistent.
- **Known judgment call:** Step 4 is manual (browser upload) because Whishper has
  no documented one-shot CLI transcription path; this is the smallest reliable
  end-to-end check.
