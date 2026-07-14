from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class Config:
    ollama_host: str
    model: str
    temperature: float
    max_chunk_words: int
    profiles_dir: str
    diarizer_host: str


def load_config(env: Optional[Mapping[str, str]] = None) -> Config:
    e = os.environ if env is None else env
    return Config(
        ollama_host=e.get("OLLAMA_HOST", "http://host.docker.internal:11434"),
        model=e.get("FORMATTER_MODEL", "qwen2.5:7b-instruct"),
        temperature=float(e.get("FORMATTER_TEMPERATURE", "0.2")),
        max_chunk_words=int(e.get("FORMATTER_MAX_CHUNK_WORDS", "800")),
        profiles_dir=e.get("FORMATTER_PROFILES_DIR", "/app/profiles"),
        diarizer_host=e.get("DIARIZER_HOST", "http://host.docker.internal:8090"),
    )
