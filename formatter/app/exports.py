from __future__ import annotations

import re
from typing import Dict, List

_EMPHASIS = re.compile(r"\*(.+?)\*")


def format_timestamp(seconds: float, comma: bool = True) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    sep = "," if comma else "."
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _italic_html(text: str) -> str:
    return _EMPHASIS.sub(r"<i>\1</i>", text).replace("\n\n", "\n")


def _strip_md(text: str) -> str:
    return _EMPHASIS.sub(r"\1", text)


def _label(seg: Dict, template: str) -> str:
    return template.format(seg["speaker"]) if seg.get("speaker") else ""


def to_srt(segments: List[Dict]) -> str:
    lines: List[str] = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(
            f'{format_timestamp(seg["start"])} --> {format_timestamp(seg["end"])}'
        )
        lines.append(f'{_label(seg, "{0}: ")}{_italic_html(seg["text"])}')
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def to_vtt(segments: List[Dict]) -> str:
    out: List[str] = ["WEBVTT", ""]
    for seg in segments:
        out.append(
            f'{format_timestamp(seg["start"], comma=False)} --> '
            f'{format_timestamp(seg["end"], comma=False)}'
        )
        body = _italic_html(seg["text"])
        if seg.get("speaker"):
            out.append(f'<v {seg["speaker"]}>{body}</v>')
        else:
            out.append(body)
        out.append("")
    return "\n".join(out).strip() + "\n"


def to_txt(segments: List[Dict]) -> str:
    paras = [f'{_label(seg, "{0}: ")}{_strip_md(seg["text"])}' for seg in segments]
    return "\n\n".join(paras).strip() + "\n"


def to_markdown(segments: List[Dict]) -> str:
    paras = [f'{_label(seg, "**{0}:** ")}{seg["text"]}' for seg in segments]
    return "\n\n".join(paras).strip() + "\n"
