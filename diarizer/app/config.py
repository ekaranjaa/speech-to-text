from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class DiarizerConfig:
    port: int
    hf_token: Optional[str]
    whisper_model: str
    device: str
    model_cache: str


def load_config(env: Optional[Mapping[str, str]] = None) -> DiarizerConfig:
    env = env if env is not None else os.environ
    return DiarizerConfig(
        port=int(env.get("DIARIZER_PORT", "8090")),
        hf_token=env.get("HF_TOKEN") or None,
        whisper_model=env.get("DIARIZER_WHISPER_MODEL", "medium"),
        device=env.get("DIARIZER_DEVICE", "auto"),
        model_cache=env.get("DIARIZER_MODEL_CACHE", "./whishper_data/models"),
    )
