from __future__ import annotations

import re

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _word_count(s: str) -> int:
    return len(s.split())


def _units(text: str, max_words: int) -> list[str]:
    units: list[str] = []
    for para in _PARAGRAPH_SPLIT.split(text):
        para = para.strip()
        if not para:
            continue
        if _word_count(para) <= max_words:
            units.append(para)
        else:
            units.extend(s for s in _SENTENCE_SPLIT.split(para) if s.strip())
    return units


def split_transcript(text: str, max_words: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for unit in _units(text, max_words):
        w = _word_count(unit)
        if current and current_words + w > max_words:
            chunks.append("\n\n".join(current))
            current = []
            current_words = 0
        current.append(unit)
        current_words += w
    if current:
        chunks.append("\n\n".join(current))
    return chunks
