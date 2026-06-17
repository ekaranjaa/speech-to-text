# GPU branch design — cross-vendor (Vulkan-first) speech-to-text

**Date:** 2026-06-17
**Status:** Approved (design), pending implementation plan

## Summary

Add a dedicated long-lived `gpu` branch to this repo that **replaces the entire
stack** rather than tweaking the existing one. `main` remains the CPU-only
Whishper stack (tuned for Apple Silicon / arm64). The `gpu` branch becomes a
**whisper.cpp + Vulkan** stack: Vulkan-accelerated and cross-vendor
(AMD / Intel / NVIDIA via the Vulkan API). Switching branches switches stacks.

One repo, two branches, clearly documented — chosen over multiple repos to keep
a small tool maintainable for the few people who use it.

## Background & constraints

- The current stack is **Whishper**, whose engine is **faster-whisper** →
  **CTranslate2**. CTranslate2's GPU backend is **CUDA-only**; it has no ROCm
  backend, so the stock stack cannot use an AMD GPU (it silently falls back to
  CPU).
- Target hardware for the first user is an **AMD PRO A8-8600B** APU
  ("Carrizo", ~2015): Radeon R6, **GCN 3rd-gen (gfx8 / gfx801)**, ~384 shaders.
  - **ROCm does not support this chip at all** (modern ROCm targets gfx900+ and
    a few recent APUs). ROCm is off the table for this box.
  - **Vulkan does run** on the iGPU, so whisper.cpp's Vulkan backend works —
    but on a 6-CU 2015 part the speedup over the 4 CPU cores is modest and may
    be near break-even for larger models.
- Reframe: this branch is **not** "make the A8-8600B fast" (it can't be). It is
  "add a cross-vendor GPU stack to the repo" that genuinely helps users with
  capable AMD/Intel/NVIDIA GPUs, while still *running* on the Carrizo dev box.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Packaging | Long-lived `gpu` branch | One repo; branch switch swaps the whole stack |
| Engine | **whisper.cpp** | Only cross-vendor GPU path; Vulkan covers all vendors |
| GPU backend default | **Vulkan** | The only path that accelerates on the Carrizo target; cross-vendor |
| ROCm | **Opt-in, documented** | Not applicable to Carrizo; useful for gfx900+ users |
| UI | whisper.cpp built-in server page | Real browser UI (upload → transcribe → download), lighter than Whishper |
| Translation service | **Drop LibreTranslate** | whisper.cpp does translate-to-English natively; re-add as opt-in if needed |
| Job DB | **Drop mongo** | Not needed without Whishper's library backend |
| Host port | **8083** (unchanged) | Preserve muscle memory from `main` |

## Architecture (gpu branch)

A single service replaces the three-service Whishper stack:

| Service | Role | Host-exposed? |
|---|---|---|
| `whisper` | whisper.cpp HTTP server, **Vulkan** backend + built-in web page | yes, **http://localhost:8083** (`8083:8080`) |

Dropped relative to `main`: `mongo` and `translate` (LibreTranslate).

### Vulkan-in-Docker plumbing

- Image: a **Vulkan-enabled whisper.cpp server** build. Verify an existing
  published tag during implementation; build a small local image if none is
  suitable. The image must contain Mesa Vulkan drivers (RADV).
- Container access to the GPU:
  - pass through `/dev/dri` device(s)
  - `group_add` the host **`render`** group (GID is host-specific; document how
    to find it: `getent group render`)
- **ROCm path (opt-in, documented only):** for gfx900+ users, note how a
  ROCm-enabled whisper.cpp build + `/dev/kfd` passthrough would be substituted.
  Explicitly state this does **not** apply to the Carrizo target.

### Data & models

- whisper.cpp uses `ggml-*.bin` model files (different from faster-whisper's
  CTranslate2 model layout).
- Persist under `./whisper_data/models` (git-ignored — same pattern as `main`).
- `.env.example` gains a `WHISPER_MODEL` variable (e.g. `medium`) and any
  server flags (threads, language). Remove `main`'s mongo/LibreTranslate/
  Whishper-specific variables (`WHISPER_MODELS`, `WHISHPER_HOST`, `LT_LOAD_ONLY`,
  `DB_USER`, `DB_PASS`).

### UI

- whisper.cpp's built-in server page: upload a file → transcribe → download
  **SRT / VTT / JSON / TXT** (the server's `response_format` options).
- Documented honestly as a lighter UI than Whishper's library manager.

## Documentation

- **`gpu` branch `README`** rewritten for this stack:
  - Prominent banner: *"This is the GPU (AMD / Vulkan) branch. `main` is the
    CPU / Whishper branch."*
  - Prerequisites: Linux host + Mesa Vulkan + `/dev/dri` access.
  - Quick start (`docker compose up -d`, open `http://localhost:8083`).
  - ROCm opt-in note (and that it does not apply to Carrizo).
  - Candid **Limitations** section: no library manager; translate-to-English
    only (no arbitrary-language subtitle translation); Carrizo performance is
    modest.
- **`main` `README`** gets a short pointer to the `gpu` branch (otherwise
  untouched).

## Testing / verification

- `docker compose config` validates on the `gpu` branch.
- Stack starts; `http://localhost:8083` serves the whisper.cpp page.
- A short audio clip transcribes and exports SRT/VTT/JSON/TXT.
- Verify Vulkan is actually used (server/log reports a Vulkan device) on a
  Vulkan-capable host; document the expected log line.
- On the Carrizo box: confirm it *runs* via Vulkan (performance is explicitly
  not a pass/fail criterion).

## Scope / non-goals

- **No NVIDIA-CUDA Whishper GPU variant** (an earlier candidate path; superseded
  by the AMD/Vulkan choice).
- **No custom rich UI build now** — the light built-in UI ships first; a richer
  front-end container remains a documented "later" option.
- **No ROCm build shipped** — documented as opt-in guidance only.

## Open items for the implementation plan

- Confirm the exact whisper.cpp server image tag with Vulkan support (or define
  the local Dockerfile).
- Confirm the server's flags for model path, port, language, and threads.
- Decide model download approach (bundled script vs. first-run download) and the
  default model in `.env.example`.
