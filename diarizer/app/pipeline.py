from __future__ import annotations

from typing import Optional

from app.engines import Diarizer, Transcriber
from app.merge import build_segments


def run_diarization(
    audio_path: str,
    transcriber: Transcriber,
    diarizer: Diarizer,
    num_speakers: Optional[int] = None,
) -> dict:
    words, language = transcriber.transcribe(audio_path)
    turns = diarizer.diarize(audio_path, num_speakers)
    segments = build_segments(words, turns)
    speakers = sorted({s["speaker"] for s in segments})
    return {"segments": segments, "speakers": speakers, "language": language}
