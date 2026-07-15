from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app.config import DiarizerConfig, load_config
from app.engines import Diarizer, DiarizerConfigError, Transcriber, build_real_engines
from app.pipeline import run_diarization


def create_app(
    config: Optional[DiarizerConfig] = None,
    transcriber: Optional[Transcriber] = None,
    diarizer: Optional[Diarizer] = None,
) -> FastAPI:
    config = config or load_config()
    app = FastAPI(title="Transcript Diarizer")
    app.state.config = config
    app.state.transcriber = transcriber
    app.state.diarizer = diarizer

    def _engines():
        if app.state.transcriber is None or app.state.diarizer is None:
            t, d = build_real_engines(app.state.config)
            app.state.transcriber, app.state.diarizer = t, d
        return app.state.transcriber, app.state.diarizer

    @app.get("/health")
    def health():
        return {
            "ready": bool(app.state.config.hf_token),
            "device": app.state.config.device,
            "model": app.state.config.whisper_model,
        }

    @app.post("/diarize")
    async def diarize(
        audio: UploadFile = File(...),
        num_speakers: Optional[int] = Form(None),
    ):
        data = await audio.read()
        if not data:
            raise HTTPException(400, "Audio file is empty.")
        try:
            transcriber, diar = _engines()
        except DiarizerConfigError as exc:
            raise HTTPException(503, str(exc))
        except Exception as exc:  # model download / load failure
            raise HTTPException(500, f"Diarization engine failed to load: {exc}")
        suffix = Path(audio.filename or "audio").suffix or ".wav"
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
                tmp.write(data)
                tmp.flush()
                return run_diarization(tmp.name, transcriber, diar, num_speakers)
        except Exception as exc:  # transcription / diarization failure
            raise HTTPException(500, f"Diarization failed: {exc}")

    return app
