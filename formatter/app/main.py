from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import Config, load_config
from app.formatting import format_transcript
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


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_store(request: Request) -> ProfileStore:
    return request.app.state.store


def get_client(request: Request) -> OllamaClient:
    return request.app.state.client


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

    @app.get("/")
    def format_page(request: Request, store: ProfileStore = Depends(get_store)):
        return templates.TemplateResponse(
            "format.html", {"request": request, "profiles": store.list()}
        )

    @app.get("/manage")
    def manage_page(request: Request):
        return templates.TemplateResponse("profiles.html", {"request": request})

    return app
