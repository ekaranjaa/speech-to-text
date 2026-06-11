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
