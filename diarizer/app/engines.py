from __future__ import annotations

from typing import Dict, List, Optional, Protocol, Tuple


class Transcriber(Protocol):
    def transcribe(self, audio_path: str) -> Tuple[List[Dict], str]:
        """Return (words, language). words: [{start, end, word}]."""
        ...


class Diarizer(Protocol):
    def diarize(self, audio_path: str, num_speakers: Optional[int]) -> List[Dict]:
        """Return speaker turns: [{start, end, speaker}]."""
        ...


class DiarizerConfigError(RuntimeError):
    pass


def resolve_device(requested: str, torch_module) -> str:
    """'auto' -> 'mps' if available else 'cpu'. Explicit values pass through."""
    if requested != "auto":
        return requested
    mps = getattr(torch_module.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


def build_real_engines(config) -> Tuple[Transcriber, Diarizer]:
    """Construct production engines. Validates the HF token BEFORE importing torch
    so a missing token fails fast with a clear, testable error."""
    if not config.hf_token:
        raise DiarizerConfigError(
            "HF_TOKEN is not set. Create a token, accept the model terms at "
            "https://hf.co/pyannote/speaker-diarization-3.1, and add HF_TOKEN to "
            "diarizer/.env."
        )
    import torch  # deferred: heavy, only needed for real inference

    device = resolve_device(config.device, torch)
    return (
        FasterWhisperTranscriber(config.whisper_model, config.model_cache),
        PyannoteDiarizer(config.hf_token, device),
    )


class FasterWhisperTranscriber:
    """faster-whisper adapter. CTranslate2 has no Metal backend, so on Apple
    Silicon this runs CPU/int8 — the diarizer's Metal use is pyannote-side."""

    def __init__(self, model_size: str, cache_root: str):
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            model_size, device="cpu", compute_type="int8", download_root=cache_root
        )

    def transcribe(self, audio_path: str) -> Tuple[List[Dict], str]:
        segments, info = self._model.transcribe(audio_path, word_timestamps=True)
        words = [
            {"start": w.start, "end": w.end, "word": w.word}
            for seg in segments
            for w in (seg.words or [])
        ]
        return words, info.language


class PyannoteDiarizer:
    def __init__(self, hf_token: str, device: str):
        import torch
        from pyannote.audio import Pipeline

        self._pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=hf_token
        )
        self._pipeline.to(torch.device(device))

    def diarize(self, audio_path: str, num_speakers: Optional[int]) -> List[Dict]:
        kwargs = {"num_speakers": num_speakers} if num_speakers else {}
        annotation = self._pipeline(audio_path, **kwargs)
        return [
            {"start": turn.start, "end": turn.end, "speaker": speaker}
            for turn, _, speaker in annotation.itertracks(yield_label=True)
        ]
