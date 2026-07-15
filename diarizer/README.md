# Diarizer (Subsystem A)

Host-native service that turns an audio file into a speaker-labeled, timestamped
transcript: faster-whisper (words) + pyannote (speakers), merged. Runs **on the
host, not in Docker** — like Ollama — so pyannote can use the Metal GPU.

## Setup (one time)

Requires **Python 3.11 or 3.12** (torch/pyannote have no 3.14 wheels):

```bash
cd diarizer
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Get a HuggingFace token (free): create an account, accept the terms at
<https://hf.co/pyannote/speaker-diarization-3.1>, generate a token, and paste it
into `diarizer/.env` as `HF_TOKEN=...`. Inference stays 100% local — only the
one-time model download needs the token.

## Run

```bash
source .venv/bin/activate
./run.sh                       # serves http://127.0.0.1:8090
curl -s localhost:8090/health  # {"ready":true,"device":"auto","model":"medium"}
```

`ready` is `false` until `HF_TOKEN` is set. The first `/diarize` call downloads
the whisper + pyannote models (slow, one time) and fails with a clear message if
the token is missing or the model terms aren't accepted.

## Diarize

```bash
curl -s -F "audio=@meeting.wav" localhost:8090/diarize | jq
# {"segments":[{"start":..,"end":..,"speaker":"SPEAKER_00","text":".."}],
#  "speakers":["SPEAKER_00","SPEAKER_01"],"language":"en"}
```

Optional `-F num_speakers=2` when you know the count.

## Notes

- **faster-whisper is CPU/int8 on Apple Silicon** — CTranslate2 has no Metal
  backend. Only pyannote uses the Metal device (`DIARIZER_DEVICE=auto`).
- The model cache defaults to `../whishper_data/models`, shared with Whishper so
  whisper weights aren't stored twice.
- Subsystem B (the formatter, in Docker) reaches this service at
  `http://host.docker.internal:${DIARIZER_PORT}` — wired in B's plan.

## Tests

Unit tests inject fakes and never import torch/pyannote, so they run on the light
deps alone:

```bash
python -m pytest        # from the diarizer/ directory
```
