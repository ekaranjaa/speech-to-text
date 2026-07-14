from __future__ import annotations

from typing import Iterator

from app.chunking import split_transcript
from app.config import Config


def format_transcript(text: str, profile: dict, client, config: Config) -> Iterator[str]:
    model = profile.get("model") or config.model
    temperature = profile.get("temperature")
    if temperature is None:
        temperature = config.temperature
    system = profile["instructions"]

    chunks = split_transcript(text, config.max_chunk_words)
    for index, chunk in enumerate(chunks):
        if index > 0:
            yield "\n\n"
        for token in client.chat(model, system, chunk, temperature):
            yield token
