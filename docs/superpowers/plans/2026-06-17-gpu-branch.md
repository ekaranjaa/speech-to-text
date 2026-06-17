# GPU branch (cross-vendor / Vulkan) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a long-lived `gpu` branch whose stack is whisper.cpp with the Vulkan backend (cross-vendor GPU), replacing the CPU-only Whishper stack that stays on `main`.

**Architecture:** A single-service Docker Compose stack — one `whisper` container running `whisper-server` (whisper.cpp) compiled with Vulkan, exposing its built-in web UI + `/inference` API on host port 8083. GPU access via `/dev/dri` passthrough and the host `render` group. Models (`ggml-*.bin`) persist under `./whisper_data/models`. No mongo, no LibreTranslate.

**Tech Stack:** Docker Compose, whisper.cpp (`whisper-server`, Vulkan/Mesa RADV), ggml model files.

**Spec:** `docs/superpowers/specs/2026-06-17-gpu-branch-design.md`

**Verification note:** This is an infrastructure/docs change, not a unit-tested library. "Tests" here are `docker compose config` validation, image smoke tests, and live `curl`/browser checks against the running server, each with explicit expected output.

---

## File structure (on the `gpu` branch)

- Rewrite: `docker-compose.yml` — single `whisper` service (was three services)
- Rewrite: `.env.example` — whisper.cpp vars (was Whishper/mongo/LT vars)
- Rewrite: `README.md` — GPU branch docs with banner + limitations
- Modify: `.gitignore` — ignore `whisper_data/` (new) alongside/instead of `whishper_data/`
- Unchanged: `docs/superpowers/**` (carried from `main`)

On `main` only (separate, final task): add a pointer paragraph to `README.md`.

---

## Task 1: Create the `gpu` branch

**Files:** none (git only)

- [ ] **Step 1: Confirm clean tree on main**

Run: `git status --porcelain && git branch --show-current`
Expected: no output from the first command (clean), and `main` printed.

- [ ] **Step 2: Create and switch to the `gpu` branch**

Run: `git switch -c gpu`
Expected: `Switched to a new branch 'gpu'`

- [ ] **Step 3: Verify the spec + plan came along**

Run: `ls docs/superpowers/specs/2026-06-17-gpu-branch-design.md docs/superpowers/plans/2026-06-17-gpu-branch.md`
Expected: both paths listed (no "No such file").

---

## Task 2: Select and smoke-test a Vulkan whisper.cpp server image

The official `ghcr.io/ggml-org/whisper.cpp:main-vulkan` image is built around the CLI; it may or may not ship the `whisper-server` binary. Determine which image to use and record it. Prefer the official image; fall back to the known server image.

**Files:** none yet (records a value used in Task 4)

- [ ] **Step 1: Pull the official Vulkan image**

Run: `docker pull ghcr.io/ggml-org/whisper.cpp:main-vulkan`
Expected: pull completes, ends with `Status: ...` line (no auth error).

- [ ] **Step 2: Check whether it contains the server binary**

Run: `docker run --rm --entrypoint sh ghcr.io/ggml-org/whisper.cpp:main-vulkan -c 'command -v whisper-server || ls /app /usr/local/bin 2>/dev/null'`
Expected: EITHER a path to `whisper-server` (→ use option A below) OR a listing without it (→ use option B).

- [ ] **Step 3: Record the chosen image**

If `whisper-server` exists, set for the rest of this plan:
`WHISPER_IMAGE = ghcr.io/ggml-org/whisper.cpp:main-vulkan` (option A — provide a `command:` in compose).

If it does NOT exist, pull and use the ready-made Vulkan server image instead:

Run: `docker pull ghcr.io/kth8/whisper-server-vulkan:latest`
Expected: pull completes.
Then set `WHISPER_IMAGE = ghcr.io/kth8/whisper-server-vulkan:latest` (option B — entrypoint already runs the server; we override its model path via `command`/env in Task 4).

- [ ] **Step 4: Confirm the host exposes a render node and render group**

Run: `ls -l /dev/dri && getent group render`
Expected: at least one `renderD128` device under `/dev/dri`, and a `render:x:<GID>:...` line. Note the `<GID>` number — it is used in Task 3/4.

> If `/dev/dri` is absent, the host has no usable GPU/DRI node; stop and resolve host setup before continuing (this stack requires a Linux host with Mesa Vulkan drivers).

---

## Task 3: Write the GPU `.env.example`

**Files:**
- Rewrite: `.env.example`

- [ ] **Step 1: Replace `.env.example` with whisper.cpp settings**

```bash
# ── Speech-to-Text (GPU branch) — whisper.cpp + Vulkan ──────────────────────
# Copy this file to `.env` (git-ignored) before `docker compose up`:
#     cp .env.example .env

# whisper.cpp server image. Set during setup (see plan Task 2):
#   ghcr.io/ggml-org/whisper.cpp:main-vulkan   (official, if it ships whisper-server)
#   ghcr.io/kth8/whisper-server-vulkan:latest  (ready-made Vulkan server, no-AVX)
WHISPER_IMAGE=ghcr.io/ggml-org/whisper.cpp:main-vulkan

# ggml model file used by the server. Downloaded into ./whisper_data/models
# (see README). Common choices: ggml-small.bin, ggml-medium.bin, ggml-large-v3-turbo.bin
WHISPER_MODEL=ggml-medium.bin

# Host port for the web UI / API (mapped to the server's internal 8080).
WHISPER_PORT=8083

# CPU threads whisper.cpp uses for the non-GPU parts of the pipeline.
WHISPER_THREADS=4

# Numeric GID of the host `render` group (find it: `getent group render`).
# Grants the container access to /dev/dri for Vulkan. REQUIRED — set to YOUR host's value.
RENDER_GID=993
```

- [ ] **Step 2: Sanity-check the file parses as env**

Run: `set -a; . ./.env.example; set +a; echo "$WHISPER_IMAGE | $WHISPER_MODEL | $WHISPER_PORT | $RENDER_GID"`
Expected: `ghcr.io/ggml-org/whisper.cpp:main-vulkan | ggml-medium.bin | 8083 | 993`

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "Add GPU-branch .env.example for whisper.cpp + Vulkan"
```

---

## Task 4: Write the single-service `docker-compose.yml`

**Files:**
- Rewrite: `docker-compose.yml`

- [ ] **Step 1: Replace `docker-compose.yml`**

Use this for **option A** (official image — explicit `command:` runs the server). For **option B** (kth8 server image), delete the `command:` block (its entrypoint already starts the server) and keep everything else; the model volume + `-m` override is supplied via `command` only in option A, so for option B also set the model via that image's documented env/flag — see the image notes recorded in Task 2.

```yaml
# Speech-to-Text — GPU branch: whisper.cpp + Vulkan (cross-vendor).
# Single service. Replaces the CPU-only Whishper stack on `main`.
# Requires a Linux host with Mesa Vulkan drivers and /dev/dri.
# Visit the UI at http://localhost:8083.

services:
  # whisper.cpp HTTP server with the Vulkan backend. Serves a built-in web page
  # (upload -> transcribe -> download SRT/VTT/JSON/TXT) and an /inference API.
  whisper:
    image: ${WHISPER_IMAGE:-ghcr.io/ggml-org/whisper.cpp:main-vulkan}
    container_name: whisper-gpu
    restart: unless-stopped
    ports:
      - ${WHISPER_PORT:-8083}:8080
    # GPU access for Vulkan: pass through the DRI render node and join the
    # host's render group so the container can use /dev/dri.
    devices:
      - /dev/dri:/dev/dri
    group_add:
      - ${RENDER_GID:-993}
    volumes:
      # Persist downloaded ggml models so they are not re-fetched on recreate.
      - ./whisper_data/models:/models
      # Optional: a place for input/output files if you script the API.
      - ./whisper_data/uploads:/uploads
    # Option A (official image): explicitly launch the server against the model.
    # For Option B (kth8 server image) remove this command block.
    command: >
      whisper-server
      --host 0.0.0.0
      --port 8080
      -m /models/${WHISPER_MODEL:-ggml-medium.bin}
      -t ${WHISPER_THREADS:-4}
```

- [ ] **Step 2: Validate compose syntax (with env)**

Run: `cp .env.example .env && docker compose config >/dev/null && echo OK`
Expected: `OK` (no YAML/interpolation errors).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "Add GPU-branch docker-compose (whisper.cpp + Vulkan, single service)"
```

---

## Task 5: Fetch a model and verify the stack runs with Vulkan

**Files:** none (runtime data under `./whisper_data/`, git-ignored)

- [ ] **Step 1: Download the default model into the models volume**

Run:
```bash
mkdir -p whisper_data/models
curl -L -o whisper_data/models/ggml-medium.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin
```
Expected: a ~1.5 GB `whisper_data/models/ggml-medium.bin` file (`ls -lh` shows it).

- [ ] **Step 2: Start the stack**

Run: `docker compose up -d && docker compose ps`
Expected: `whisper-gpu` shows `running`/`Up`.

- [ ] **Step 3: Confirm Vulkan device was selected (not silent CPU fallback)**

Run: `docker compose logs whisper | grep -iE 'vulkan|ggml_vulkan|using device' | head`
Expected: a line naming a Vulkan device (e.g. `ggml_vulkan: Found ... GPU` / `Using Vulkan0 (...)`). If no Vulkan line appears, GPU access is misconfigured — recheck `RENDER_GID` and `/dev/dri` (see README troubleshooting).

- [ ] **Step 4: Confirm the web UI is served**

Run: `curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:8083/`
Expected: `200`.

- [ ] **Step 5: Transcribe a short clip and export SRT**

Run:
```bash
docker run --rm -v "$PWD/whisper_data:/w" ghcr.io/ggml-org/whisper.cpp:main-vulkan \
  sh -c 'ffmpeg -y -f lavfi -i "sine=frequency=440:duration=3" -ac 1 -ar 16000 /w/uploads/test.wav' 2>/dev/null
curl -fsS http://localhost:8083/inference \
  -F file=@whisper_data/uploads/test.wav \
  -F response_format=srt
```
Expected: an HTTP 200 with SRT-formatted text (lines like `1` / `00:00:00,000 --> ...`). (Content may be empty/garbled for a sine tone — the goal is a valid SRT response, proving the pipeline works.)

- [ ] **Step 6: Spot-check the other formats**

Run: `for f in vtt json text; do echo "== $f =="; curl -fsS http://localhost:8083/inference -F file=@whisper_data/uploads/test.wav -F response_format=$f | head -3; done`
Expected: `WEBVTT` header for vtt, a JSON object for json, plain text for text.

- [ ] **Step 7: Tear down**

Run: `docker compose down`
Expected: containers removed; `whisper_data/` retained.

---

## Task 6: Rewrite `README.md` for the GPU branch

**Files:**
- Rewrite: `README.md`

- [ ] **Step 1: Replace `README.md`**

```markdown
# speech-to-text — GPU branch (whisper.cpp + Vulkan)

> ⚠️ **This is the GPU branch.** It runs a **whisper.cpp + Vulkan** stack for
> GPU-accelerated transcription on **AMD / Intel / NVIDIA** GPUs (cross-vendor,
> via the Vulkan API). The default branch **`main`** runs the CPU-only
> **Whishper** stack (Apple Silicon / arm64). Switching branches switches the
> whole stack — they do not share a UI or data format.

Self-hosted speech-to-text that transcribes audio into transcripts and
subtitles (SRT / VTT / JSON / TXT) from a browser, GPU-accelerated through
[whisper.cpp](https://github.com/ggml-org/whisper.cpp).

## Requirements

- A **Linux host** with **Mesa Vulkan drivers** installed and a DRI render node
  at `/dev/dri` (`ls /dev/dri` should show `renderD128`).
- Docker + Docker Compose.
- A Vulkan-capable GPU. Any vendor works via Vulkan; see *ROCm* below for an
  AMD-specific speed option.

## Stack

One container (see `docker-compose.yml`):

| Service | Role | Host-exposed? |
|---|---|---|
| `whisper` | whisper.cpp HTTP server (Vulkan) + built-in web page + `/inference` API | yes, **http://localhost:8083** |

No `mongo` and no LibreTranslate (both were Whishper-specific). whisper.cpp can
translate speech **to English** natively; arbitrary-language subtitle
translation is **not** available on this branch (see *Limitations*).

## Quick start

```bash
cp .env.example .env                  # then edit RENDER_GID for your host
getent group render                   # <- put this GID into RENDER_GID in .env

mkdir -p whisper_data/models          # download the default model:
curl -L -o whisper_data/models/ggml-medium.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin

docker compose up -d
```

Then open **http://localhost:8083**, upload a file, and download the transcript
in your chosen format.

```bash
docker compose logs -f whisper   # follow logs (look for a "Vulkan" device line)
docker compose ps                # service status
docker compose down              # stop (models kept under ./whisper_data)
```

## Configuration (`.env`)

| Variable | Meaning | Default |
|---|---|---|
| `WHISPER_IMAGE` | whisper.cpp server image (Vulkan) | `ghcr.io/ggml-org/whisper.cpp:main-vulkan` |
| `WHISPER_MODEL` | ggml model file under `./whisper_data/models` | `ggml-medium.bin` |
| `WHISPER_PORT` | host port for the UI/API | `8083` |
| `WHISPER_THREADS` | CPU threads for non-GPU pipeline parts | `4` |
| `RENDER_GID` | host `render` group GID for `/dev/dri` access — **set this** | `993` |

Models come from <https://huggingface.co/ggerganov/whisper.cpp>
(`ggml-small.bin`, `ggml-medium.bin`, `ggml-large-v3-turbo.bin`, …).

## ROCm (optional, AMD only)

Vulkan is the cross-vendor default and works on most AMD cards. On
**ROCm-supported** Radeon GPUs (roughly gfx900 / Vega and newer) a ROCm build of
whisper.cpp can be faster: swap `WHISPER_IMAGE` for a ROCm server image and add
`/dev/kfd` passthrough. **This does not apply to older APUs** such as the AMD
A8-8600B (Carrizo / gfx8), which are not supported by ROCm — use Vulkan there.

## Limitations

- **Lighter UI than `main`.** whisper.cpp's built-in page is upload → transcribe
  → download. There is no transcription library/manager or in-browser subtitle
  editor like Whishper. A richer front-end could be added later.
- **Translate-to-English only.** No arbitrary-language subtitle translation
  (that was LibreTranslate on `main`).
- **Old/integrated GPUs are modest.** A weak iGPU (e.g. AMD A8-8600B, 6 CUs)
  runs via Vulkan but may be only marginally faster than CPU.

## Data

Everything persists under `./whisper_data/` (git-ignored): `models/` (ggml
models) and `uploads/` (optional working files). Delete a subfolder to reset it.

## Troubleshooting

- **No Vulkan device in logs / slow CPU-only runs:** confirm `/dev/dri` exists,
  `RENDER_GID` matches `getent group render`, and Mesa Vulkan drivers are
  installed on the host. `docker compose logs whisper | grep -i vulkan` should
  name a GPU.
- **`whisper-server: not found` on startup:** your `WHISPER_IMAGE` doesn't ship
  the server binary — use a server image (e.g.
  `ghcr.io/kth8/whisper-server-vulkan:latest`) and remove the `command:` block.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Rewrite README for GPU branch (whisper.cpp + Vulkan)"
```

---

## Task 7: Update `.gitignore` for the new data dir

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add `whisper_data/` to `.gitignore`**

Change the runtime-data block so it ignores the new directory (keep the old line
too — harmless, and avoids accidental commits if someone checks out across
branches):

```
# Runtime data: downloaded ggml models, uploads/working files. Can be large
# (multi-GB) and is machine-local — never commit it.
whisper_data/
whishper_data/
```

- [ ] **Step 2: Verify the data dir is ignored**

Run: `git check-ignore whisper_data/models/ggml-medium.bin`
Expected: the path is printed (meaning it is ignored).

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "Ignore whisper_data/ runtime directory on GPU branch"
```

---

## Task 8: Add a pointer to the `gpu` branch from `main`

This is the only change that lands on **`main`**, not `gpu`.

**Files:**
- Modify (on `main`): `README.md`

- [ ] **Step 1: Switch to main**

Run: `git switch main`
Expected: `Switched to branch 'main'`

- [ ] **Step 2: Add a GPU-branch note near the top of `README.md`**

Insert this block immediately after the opening description paragraph (after the
line ending "…and it runs entirely locally."):

```markdown

> **Need GPU acceleration?** This `main` branch is CPU-only (Whishper, tuned for
> Apple Silicon). A separate **`gpu`** branch runs a cross-vendor
> **whisper.cpp + Vulkan** stack for AMD / Intel / NVIDIA GPUs on Linux:
> `git switch gpu`. It's a different stack with a lighter UI — see that branch's
> README.
```

- [ ] **Step 3: Update the existing "GPU" bullet at the bottom of `README.md`**

Replace the final bullet:

```markdown
- **GPU:** not available under Docker on macOS; this stack is CPU-only by design.
```

with:

```markdown
- **GPU:** not available under Docker on macOS, so this `main` stack is CPU-only
  by design. For GPU acceleration on a Linux host, use the **`gpu`** branch
  (`git switch gpu`) — a whisper.cpp + Vulkan stack.
```

- [ ] **Step 4: Commit on main**

```bash
git add README.md
git commit -m "Point to the gpu branch from the main README"
```

---

## Task 9: Final verification

- [ ] **Step 1: Confirm both branches are coherent**

Run:
```bash
git switch gpu && docker compose config >/dev/null && echo "gpu OK"
git switch main && grep -q 'gpu' README.md && echo "main pointer OK"
```
Expected: `gpu OK` and `main pointer OK`.

- [ ] **Step 2: Review the GPU branch diff vs main**

Run: `git diff main gpu -- docker-compose.yml .env.example README.md .gitignore | head -40`
Expected: shows the stack swap (single whisper service, whisper.cpp vars, new README). Sanity-check nothing from the Whishper stack leaked through.

- [ ] **Step 3: Decide integration**

Both branches are pushed/kept as long-lived branches (no merge of `gpu` into
`main` — they are intentionally divergent stacks). Use the
`superpowers:finishing-a-development-branch` skill to choose how to publish
(e.g. `git push -u origin gpu`).

---

## Self-review notes

- **Spec coverage:** branch (T1), whisper.cpp+Vulkan engine (T2,T4,T5), Vulkan
  device plumbing /dev/dri + render group (T2,T4,T5), drop mongo+LibreTranslate
  (T4), port 8083 (T3,T4), model persistence under whisper_data/models (T5,T7),
  light built-in UI + SRT/VTT/JSON/TXT (T5,T6), README banner + ROCm opt-in +
  limitations (T6), main README pointer (T8). ROCm shipped as docs-only (T6) ✓.
- **Known unknown handled:** whether the official image ships `whisper-server`
  is resolved explicitly in T2 with a concrete fallback image, and surfaced in
  README troubleshooting (T6).
- **Naming consistency:** `WHISPER_IMAGE`, `WHISPER_MODEL`, `WHISPER_PORT`,
  `WHISPER_THREADS`, `RENDER_GID`, dir `whisper_data/` used identically across
  `.env.example`, compose, README, and gitignore.
