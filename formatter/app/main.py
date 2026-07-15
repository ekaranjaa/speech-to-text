from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import Config, load_config
from app.diarizer_client import DiarizerClient, DiarizerUnreachable
from app.exports import to_markdown, to_srt, to_txt, to_vtt
from app.formatting import format_segments, format_transcript
from app.ollama_client import OllamaClient
from app.profiles import DuplicateProfile, ProfileNotFound, ProfileStore

_APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_APP_DIR / "templates"))


class ProfileBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None


class FormatRequest(BaseModel):
    text: str
    profile_id: str
    model: Optional[str] = None
    temperature: Optional[float] = None


class SegmentsFormatRequest(BaseModel):
    segments: list[dict]
    profile_id: str
    model: Optional[str] = None
    temperature: Optional[float] = None


class ExportRequest(BaseModel):
    segments: list[dict]
    format: str


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_store(request: Request) -> ProfileStore:
    return request.app.state.store


def get_client(request: Request) -> OllamaClient:
    return request.app.state.client


def get_diarizer(request: Request) -> DiarizerClient:
    return request.app.state.diarizer


def _model_available(model: str, available: list[str]) -> bool:
    if model in available:
        return True
    base = model.split(":")[0]
    return any(a == base or a.split(":")[0] == base for a in available)


def create_app(config: Optional[Config] = None) -> FastAPI:
    config = config or load_config()
    app = FastAPI(title="Transcript Formatter")

    store = ProfileStore(config.profiles_dir)
    store.seed_if_empty()

    app.state.config = config
    app.state.store = store
    app.state.client = OllamaClient(config.ollama_host)
    app.state.diarizer = DiarizerClient(config.diarizer_host)

    (_APP_DIR / "templates").mkdir(parents=True, exist_ok=True)
    static_dir = _APP_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/api/health")
    def health(client: OllamaClient = Depends(get_client)):
        return client.health()

    @app.get("/api/profiles")
    def list_profiles(store: ProfileStore = Depends(get_store)):
        return store.list()

    @app.get("/api/profiles/{profile_id}")
    def get_profile(profile_id: str, store: ProfileStore = Depends(get_store)):
        try:
            return store.get(profile_id)
        except ProfileNotFound:
            raise HTTPException(404, f"Profile '{profile_id}' not found.")

    @app.post("/api/profiles", status_code=201)
    def create_profile(body: ProfileBody, store: ProfileStore = Depends(get_store)):
        try:
            return store.create(body.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except DuplicateProfile:
            raise HTTPException(409, "A profile with that name already exists.")

    @app.put("/api/profiles/{profile_id}")
    def update_profile(
        profile_id: str, body: ProfileBody, store: ProfileStore = Depends(get_store)
    ):
        try:
            return store.update(profile_id, body.model_dump(exclude_none=True))
        except ProfileNotFound:
            raise HTTPException(404, f"Profile '{profile_id}' not found.")
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.delete("/api/profiles/{profile_id}", status_code=204)
    def delete_profile(profile_id: str, store: ProfileStore = Depends(get_store)):
        try:
            store.delete(profile_id)
        except ProfileNotFound:
            raise HTTPException(404, f"Profile '{profile_id}' not found.")

    @app.post("/api/format")
    def format_route(
        req: FormatRequest,
        store: ProfileStore = Depends(get_store),
        client: OllamaClient = Depends(get_client),
        config: Config = Depends(get_config),
    ):
        if not req.text.strip():
            raise HTTPException(400, "Transcript text is empty.")
        try:
            profile = dict(store.get(req.profile_id))
        except ProfileNotFound:
            raise HTTPException(404, f"Profile '{req.profile_id}' not found.")
        if req.model is not None:
            profile["model"] = req.model
        if req.temperature is not None:
            profile["temperature"] = req.temperature

        resolved_model = profile.get("model") or config.model
        health = client.health()
        if not health["reachable"]:
            raise HTTPException(
                503,
                f"Ollama isn't reachable at {config.ollama_host}. "
                "Start it (open the Ollama app or run `ollama serve`).",
            )
        if not _model_available(resolved_model, health["models"]):
            raise HTTPException(
                424,
                f"Model '{resolved_model}' isn't installed. "
                f"Run: ollama pull {resolved_model}",
            )

        stream = format_transcript(req.text, profile, client, config)
        return StreamingResponse(stream, media_type="text/plain; charset=utf-8")

    @app.post("/api/diarize")
    async def diarize_route(
        audio: UploadFile = File(...),
        num_speakers: Optional[int] = Form(None),
        diarizer: DiarizerClient = Depends(get_diarizer),
        config: Config = Depends(get_config),
    ):
        data = await audio.read()
        if not data:
            raise HTTPException(400, "Audio file is empty.")
        try:
            return diarizer.diarize(data, audio.filename or "audio.wav", num_speakers)
        except DiarizerUnreachable:
            raise HTTPException(
                503,
                f"Diarizer isn't reachable at {config.diarizer_host}. "
                "Start it on the host (cd diarizer && ./run.sh).",
            )

    _EXPORTERS = {"srt": to_srt, "vtt": to_vtt, "txt": to_txt, "md": to_markdown}
    _EXPORT_MEDIA = {
        "srt": "application/x-subrip",
        "vtt": "text/vtt",
        "txt": "text/plain",
        "md": "text/markdown",
    }

    @app.post("/api/format/segments")
    def format_segments_route(
        req: SegmentsFormatRequest,
        store: ProfileStore = Depends(get_store),
        client: OllamaClient = Depends(get_client),
        config: Config = Depends(get_config),
    ):
        if not req.segments:
            raise HTTPException(400, "No segments to format.")
        try:
            profile = dict(store.get(req.profile_id))
        except ProfileNotFound:
            raise HTTPException(404, f"Profile '{req.profile_id}' not found.")
        if req.model is not None:
            profile["model"] = req.model
        if req.temperature is not None:
            profile["temperature"] = req.temperature

        resolved_model = profile.get("model") or config.model
        health = client.health()
        if not health["reachable"]:
            raise HTTPException(
                503,
                f"Ollama isn't reachable at {config.ollama_host}. "
                "Start it (open the Ollama app or run `ollama serve`).",
            )
        if not _model_available(resolved_model, health["models"]):
            raise HTTPException(
                424,
                f"Model '{resolved_model}' isn't installed. "
                f"Run: ollama pull {resolved_model}",
            )

        def stream():
            for turn in format_segments(req.segments, profile, client, config):
                yield json.dumps(turn) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/api/export")
    def export_route(req: ExportRequest):
        exporter = _EXPORTERS.get(req.format)
        if exporter is None:
            raise HTTPException(400, f"Unknown format '{req.format}'.")
        text = exporter(req.segments)
        return Response(
            content=text,
            media_type=_EXPORT_MEDIA[req.format],
            headers={"Content-Disposition": f'attachment; filename="transcript.{req.format}"'},
        )

    @app.get("/manage")
    def manage_page(request: Request):
        return templates.TemplateResponse("profiles.html", {"request": request})

    # Serve the built Vue SPA at "/" when present (produced by `npm run build`
    # locally or the multi-stage Docker build). Registered last so every
    # /api/* route and /manage take precedence.
    web_dist = _APP_DIR.parent / "web" / "dist"
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="spa")

    return app
