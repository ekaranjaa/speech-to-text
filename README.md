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

To confirm the GPU is actually in use (not a silent CPU fallback):

```bash
docker compose logs whisper | grep -i vulkan   # should name your GPU
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
