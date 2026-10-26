from __future__ import annotations

from typing import Iterator

from app.chunking import split_transcript
from app.config import Config
from app.segments import group_turns


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


def format_segments(segments: list[dict], profile: dict, client, config: Config) -> Iterator[dict]:
    model = profile.get("model") or config.model
    temperature = profile.get("temperature")
    if temperature is None:
        temperature = config.temperature
    system = profile["instructions"]

    for turn in group_turns(segments):
        text = " ".join(s["text"] for s in turn).strip()
        parts = []
        for chunk in split_transcript(text, config.max_chunk_words):
            parts.append("".join(client.chat(model, system, chunk, temperature)))
        yield {
            "speaker": turn[0]["speaker"],
            "start": turn[0]["start"],
            "end": turn[-1]["end"],
            "text": "\n\n".join(p for p in parts if p).strip(),
        }
