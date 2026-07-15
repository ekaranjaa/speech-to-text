from __future__ import annotations

from typing import Dict, List


def _midpoint(word: Dict) -> float:
    return (word["start"] + word["end"]) / 2.0


def _overlap(word: Dict, turn: Dict) -> float:
    lo = max(word["start"], turn["start"])
    hi = min(word["end"], turn["end"])
    return max(0.0, hi - lo)


def _distance(mid: float, turn: Dict) -> float:
    if mid < turn["start"]:
        return turn["start"] - mid
    if mid > turn["end"]:
        return mid - turn["end"]
    return 0.0


def assign_speaker(word: Dict, turns: List[Dict], default: str = "SPEAKER_00") -> str:
    """Assign a word to the speaker whose turn best covers its midpoint.

    Prefer a turn that contains the midpoint (ties broken by largest overlap of
    the word's [start, end]); otherwise the nearest turn by distance; fall back to
    `default` when there are no turns (mono audio, silence).
    """
    if not turns:
        return default
    mid = _midpoint(word)
    containing = [t for t in turns if t["start"] <= mid <= t["end"]]
    if containing:
        return max(containing, key=lambda t: _overlap(word, t))["speaker"]
    return min(turns, key=lambda t: _distance(mid, t))["speaker"]


def build_segments(
    words: List[Dict], turns: List[Dict], default: str = "SPEAKER_00"
) -> List[Dict]:
    """Group consecutive same-speaker words into `{start, end, speaker, text}`."""
    segments: List[Dict] = []
    for word in words:
        speaker = assign_speaker(word, turns, default)
        if segments and segments[-1]["speaker"] == speaker:
            segments[-1]["end"] = word["end"]
            segments[-1]["_words"].append(word["word"])
        else:
            segments.append(
                {
                    "start": word["start"],
                    "end": word["end"],
                    "speaker": speaker,
                    "_words": [word["word"]],
                }
            )
    for seg in segments:
        seg["text"] = "".join(seg.pop("_words")).strip()
    return segments
