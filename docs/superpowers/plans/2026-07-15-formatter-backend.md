# Formatter Backend (Subsystem B1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the v1 formatter's FastAPI backend to be speaker/segment-aware: proxy audio to the host diarizer, reflow each speaker turn through a style profile, render SRT/VTT/TXT/Markdown, and upgrade the GoTranscript prompts (italics, quoting) — all additively, without breaking v1's existing routes or pages.

**Architecture:** New pure/injectable modules — `segments.py` (turn grouping), `exports.py` (renderers), `diarizer_client.py` (httpx client to the host diarizer, mirroring `OllamaClient`) — plus a `format_segments` generator in `formatting.py` and new routes in `main.py`. Existing v1 code (plain-text `/api/format`, Jinja pages, profile CRUD) is untouched. The Vue frontend (Subsystem B2) consumes these endpoints.

**Tech Stack:** Python 3.12, FastAPI, httpx (with `httpx.MockTransport` for tests), pytest. Same deps as v1 (`formatter/requirements.txt`) — no new packages.

## Global Constraints

- **Additive only:** do not modify or remove v1's `/api/format` (plain text), `/`, `/manage`, or profile CRUD. New segment endpoints live at new paths.
- **Run tests from `formatter/`** with `python -m pytest` (cwd on `sys.path`, so `from app.x import ...` resolves).
- **Segment shape** (the A→B contract): `{"start": float, "end": float, "speaker": str, "text": str}`. `text` may contain Markdown emphasis (`*italics*`) once formatted.
- **Speaker labels and timestamps are structural** — applied by export renderers, never by the LLM. Prompts keep "do not add speaker labels or timestamps."
- **Diarizer host** default `http://host.docker.internal:8090` (B's Docker container → host-native diarizer, same bridge as Ollama). Env key `DIARIZER_HOST`.
- **`/api/format/segments` streams NDJSON** — one formatted-turn JSON object per line (`application/x-ndjson`), so the UI can render turns progressively.
- **Turn = a contiguous run of same-speaker segments.** Consecutive same-speaker segments are merged into one turn (start = first.start, end = last.end); different speakers are never merged into one LLM call.
- No `docker-compose.yml`/`.env` change until Task 8; no frontend work (that's B2).

## File Structure

- `formatter/app/config.py` — **modify**: add `diarizer_host` field + `DIARIZER_HOST` env.
- `formatter/app/segments.py` — **create**: `group_turns`.
- `formatter/app/formatting.py` — **modify**: add `format_segments`.
- `formatter/app/exports.py` — **create**: `format_timestamp`, `to_srt`, `to_vtt`, `to_txt`, `to_markdown`.
- `formatter/app/diarizer_client.py` — **create**: `DiarizerClient`, `DiarizerError`, `DiarizerUnreachable`.
- `formatter/app/seed_profiles.py` — **modify**: add italics + quoting rules to both prompts.
- `formatter/app/main.py` — **modify**: wire `DiarizerClient`; add `/api/diarize`, `/api/format/segments`, `/api/export`.
- `formatter/.env.example`, repo `.env`/`.env.example`, `docker-compose.yml`, `README.md` — **modify** (Task 8).
- Tests: `test_config.py` (extend), `test_segments.py`, `test_formatting.py` (extend), `test_exports.py`, `test_diarizer_client.py`, `test_seed_profiles.py`, `test_api.py` (extend).

---

### Task 1: Config — diarizer host

**Files:**
- Modify: `formatter/app/config.py`
- Test: `formatter/tests/test_config.py` (add cases)

**Interfaces:**
- Produces: `Config.diarizer_host: str`; `load_config` reads `DIARIZER_HOST` (default `http://host.docker.internal:8090`).

- [ ] **Step 1: Write the failing test** — append to `formatter/tests/test_config.py`:

```python
def test_diarizer_host_default():
    from app.config import load_config
    assert load_config({}).diarizer_host == "http://host.docker.internal:8090"


def test_diarizer_host_override():
    from app.config import load_config
    cfg = load_config({"DIARIZER_HOST": "http://localhost:8090"})
    assert cfg.diarizer_host == "http://localhost:8090"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'diarizer_host'`.

- [ ] **Step 3: Write minimal implementation** — in `formatter/app/config.py`, add the field and loader line:

```python
@dataclass(frozen=True)
class Config:
    ollama_host: str
    model: str
    temperature: float
    max_chunk_words: int
    profiles_dir: str
    diarizer_host: str
```

```python
    return Config(
        ollama_host=e.get("OLLAMA_HOST", "http://host.docker.internal:11434"),
        model=e.get("FORMATTER_MODEL", "qwen2.5:7b-instruct"),
        temperature=float(e.get("FORMATTER_TEMPERATURE", "0.2")),
        max_chunk_words=int(e.get("FORMATTER_MAX_CHUNK_WORDS", "800")),
        profiles_dir=e.get("FORMATTER_PROFILES_DIR", "/app/profiles"),
        diarizer_host=e.get("DIARIZER_HOST", "http://host.docker.internal:8090"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_config.py -v`
Expected: PASS (existing config tests + 2 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/app/config.py formatter/tests/test_config.py
git commit -m "feat(formatter): add diarizer_host config"
```

---

### Task 2: Turn grouping

**Files:**
- Create: `formatter/app/segments.py`
- Test: `formatter/tests/test_segments.py`

**Interfaces:**
- Produces: `group_turns(segments: list[dict]) -> list[list[dict]]` — contiguous same-speaker runs, order preserved.

- [ ] **Step 1: Write the failing test** — `formatter/tests/test_segments.py`:

```python
from app.segments import group_turns


def test_group_turns_merges_consecutive_same_speaker():
    segs = [
        {"start": 0.0, "end": 1.0, "speaker": "A", "text": "one"},
        {"start": 1.0, "end": 2.0, "speaker": "A", "text": "two"},
        {"start": 2.0, "end": 3.0, "speaker": "B", "text": "three"},
        {"start": 3.0, "end": 4.0, "speaker": "A", "text": "four"},
    ]
    turns = group_turns(segs)
    assert [len(t) for t in turns] == [2, 1, 1]
    assert [t[0]["speaker"] for t in turns] == ["A", "B", "A"]


def test_group_turns_empty():
    assert group_turns([]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_segments.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.segments'`.

- [ ] **Step 3: Write minimal implementation** — `formatter/app/segments.py`:

```python
from __future__ import annotations

from typing import Dict, List


def group_turns(segments: List[Dict]) -> List[List[Dict]]:
    """Group a flat segment list into contiguous same-speaker turns."""
    turns: List[List[Dict]] = []
    for seg in segments:
        if turns and turns[-1][-1]["speaker"] == seg["speaker"]:
            turns[-1].append(seg)
        else:
            turns.append([seg])
    return turns
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_segments.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/app/segments.py formatter/tests/test_segments.py
git commit -m "feat(formatter): group segments into speaker turns"
```

---

### Task 3: Segment-aware formatting

**Files:**
- Modify: `formatter/app/formatting.py` (add `format_segments`; keep `format_transcript`)
- Test: `formatter/tests/test_formatting.py` (add cases)

**Interfaces:**
- Consumes: `group_turns` (Task 2), `split_transcript` (v1 `chunking.py`), a client with `.chat(model, system, user, temperature) -> Iterator[str]` (v1 `OllamaClient`), `Config`.
- Produces: `format_segments(segments: list[dict], profile: dict, client, config: Config) -> Iterator[dict]` — yields `{"speaker", "start", "end", "text"}` per turn. Within a turn, text is joined, chunked by `max_chunk_words`, each chunk formatted, results joined with `\n\n`.

- [ ] **Step 1: Write the failing test** — append to `formatter/tests/test_formatting.py`:

```python
from app.config import Config
from app.formatting import format_segments


class _EchoClient:
    """Returns the chunk uppercased so tests can assert transformation + grouping."""

    def chat(self, model, system, user, temperature):
        yield user.upper()


def _cfg(max_words=800):
    return Config(
        ollama_host="x", model="m", temperature=0.2,
        max_chunk_words=max_words, profiles_dir="/tmp", diarizer_host="x",
    )


def test_format_segments_one_turn_per_speaker_run():
    segs = [
        {"start": 0.0, "end": 1.0, "speaker": "A", "text": "hi there"},
        {"start": 1.0, "end": 2.0, "speaker": "A", "text": "again"},
        {"start": 2.0, "end": 3.0, "speaker": "B", "text": "yo"},
    ]
    profile = {"instructions": "sys"}
    out = list(format_segments(segs, profile, _EchoClient(), _cfg()))
    assert [o["speaker"] for o in out] == ["A", "B"]
    assert out[0] == {"speaker": "A", "start": 0.0, "end": 2.0, "text": "HI THERE AGAIN"}
    assert out[1] == {"speaker": "B", "start": 2.0, "end": 3.0, "text": "YO"}


def test_format_segments_profile_overrides_used():
    segs = [{"start": 0.0, "end": 1.0, "speaker": "A", "text": "x"}]
    seen = {}

    class _Spy:
        def chat(self, model, system, user, temperature):
            seen["model"] = model
            seen["temperature"] = temperature
            yield "ok"

    profile = {"instructions": "sys", "model": "custom", "temperature": 0.9}
    list(format_segments(segs, profile, _Spy(), _cfg()))
    assert seen == {"model": "custom", "temperature": 0.9}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_formatting.py -v`
Expected: FAIL — `ImportError: cannot import name 'format_segments'`.

- [ ] **Step 3: Write minimal implementation** — append to `formatter/app/formatting.py`:

```python
from app.segments import group_turns


def format_segments(segments, profile, client, config: Config):
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_formatting.py -v`
Expected: PASS (v1's `format_transcript` tests + 2 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/app/formatting.py formatter/tests/test_formatting.py
git commit -m "feat(formatter): segment-aware format_segments (per-turn reflow)"
```

---

### Task 4: Export renderers

**Files:**
- Create: `formatter/app/exports.py`
- Test: `formatter/tests/test_exports.py`

**Interfaces:**
- Produces: `format_timestamp(seconds: float, comma: bool = True) -> str`; `to_srt`, `to_vtt`, `to_txt`, `to_markdown`, each `(segments: list[dict]) -> str`. Markdown emphasis `*x*` → `<i>x</i>` (SRT/VTT), stripped to `x` (TXT), kept (Markdown). Speaker prefix per format.

- [ ] **Step 1: Write the failing test** — `formatter/tests/test_exports.py`:

```python
from app.exports import format_timestamp, to_markdown, to_srt, to_txt, to_vtt

SEGS = [
    {"start": 0.0, "end": 2.5, "speaker": "Interviewer", "text": "I loved *Friends*."},
    {"start": 2.5, "end": 4.0, "speaker": "Guest", "text": "Me too."},
]


def test_format_timestamp_srt_and_vtt():
    assert format_timestamp(3661.5) == "01:01:01,500"
    assert format_timestamp(3661.5, comma=False) == "01:01:01.500"


def test_to_srt():
    out = to_srt(SEGS)
    assert "1\n00:00:00,000 --> 00:00:02,500\nInterviewer: I loved <i>Friends</i>." in out
    assert "2\n00:00:02,500 --> 00:00:04,000\nGuest: Me too." in out


def test_to_vtt():
    out = to_vtt(SEGS)
    assert out.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.500\n<v Interviewer>I loved <i>Friends</i>.</v>" in out


def test_to_txt_strips_markdown():
    out = to_txt(SEGS)
    assert "Interviewer: I loved Friends." in out
    assert "Guest: Me too." in out
    assert "*" not in out and "<i>" not in out


def test_to_markdown_keeps_emphasis_and_bold_labels():
    out = to_markdown(SEGS)
    assert "**Interviewer:** I loved *Friends*." in out
    assert "**Guest:** Me too." in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_exports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.exports'`.

- [ ] **Step 3: Write minimal implementation** — `formatter/app/exports.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_exports.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/app/exports.py formatter/tests/test_exports.py
git commit -m "feat(formatter): SRT/VTT/TXT/Markdown export renderers"
```

---

### Task 5: Diarizer client

**Files:**
- Create: `formatter/app/diarizer_client.py`
- Test: `formatter/tests/test_diarizer_client.py`

**Interfaces:**
- Produces: `DiarizerClient(host, timeout=600.0, client=None)` with `.health() -> dict` (`{"reachable": bool, "ready": bool, ...}`) and `.diarize(audio: bytes, filename: str, num_speakers: Optional[int] = None) -> dict`. Exceptions `DiarizerError`, `DiarizerUnreachable`.

- [ ] **Step 1: Write the failing test** — `formatter/tests/test_diarizer_client.py`:

```python
import httpx
import pytest

from app.diarizer_client import DiarizerClient, DiarizerUnreachable


def _client(handler):
    transport = httpx.MockTransport(handler)
    return DiarizerClient("http://diarizer:8090", client=httpx.Client(transport=transport))


def test_health_reachable():
    def handler(request):
        assert request.url.path == "/health"
        return httpx.Response(200, json={"ready": True, "device": "mps", "model": "medium"})

    health = _client(handler).health()
    assert health["reachable"] is True
    assert health["ready"] is True


def test_health_unreachable_returns_flag():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    assert _client(handler).health() == {"reachable": False, "ready": False}


def test_diarize_posts_multipart_and_returns_segments():
    def handler(request):
        assert request.url.path == "/diarize"
        assert b"audiobytes" in request.content
        return httpx.Response(200, json={"segments": [{"speaker": "SPEAKER_00"}], "speakers": ["SPEAKER_00"], "language": "en"})

    result = _client(handler).diarize(b"audiobytes", "clip.wav")
    assert result["speakers"] == ["SPEAKER_00"]


def test_diarize_unreachable_raises():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(DiarizerUnreachable):
        _client(handler).diarize(b"x", "clip.wav")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_diarizer_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.diarizer_client'`.

- [ ] **Step 3: Write minimal implementation** — `formatter/app/diarizer_client.py`:

```python
from __future__ import annotations

from typing import Optional

import httpx


class DiarizerError(Exception):
    pass


class DiarizerUnreachable(DiarizerError):
    pass


class DiarizerClient:
    def __init__(self, host: str, timeout: float = 600.0, client: Optional[httpx.Client] = None):
        self._host = host.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def health(self) -> dict:
        try:
            resp = self._client.get(f"{self._host}/health")
            resp.raise_for_status()
            data = resp.json()
            return {"reachable": True, **data}
        except (httpx.ConnectError, httpx.HTTPError):
            return {"reachable": False, "ready": False}

    def diarize(self, audio: bytes, filename: str, num_speakers: Optional[int] = None) -> dict:
        files = {"audio": (filename, audio, "application/octet-stream")}
        data = {"num_speakers": str(num_speakers)} if num_speakers else {}
        try:
            resp = self._client.post(f"{self._host}/diarize", files=files, data=data)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise DiarizerUnreachable(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise DiarizerError(str(exc)) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_diarizer_client.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/app/diarizer_client.py formatter/tests/test_diarizer_client.py
git commit -m "feat(formatter): DiarizerClient (health + diarize proxy)"
```

---

### Task 6: Upgraded GoTranscript prompts

**Files:**
- Modify: `formatter/app/seed_profiles.py`
- Test: `formatter/tests/test_seed_profiles.py`

**Interfaces:**
- Produces: updated `CLEAN_VERBATIM_INSTRUCTIONS` and `FULL_VERBATIM_INSTRUCTIONS` containing an italics rule and a no-quoting-unintelligible rule. `SEED_PROFILES` structure unchanged.

- [ ] **Step 1: Write the failing test** — `formatter/tests/test_seed_profiles.py`:

```python
from app.seed_profiles import (
    CLEAN_VERBATIM_INSTRUCTIONS,
    FULL_VERBATIM_INSTRUCTIONS,
    SEED_PROFILES,
)


def test_both_prompts_have_italics_rule():
    for text in (CLEAN_VERBATIM_INSTRUCTIONS, FULL_VERBATIM_INSTRUCTIONS):
        low = text.lower()
        assert "italic" in low
        assert "film" in low and "book" in low


def test_both_prompts_forbid_quoting_unintelligible():
    for text in (CLEAN_VERBATIM_INSTRUCTIONS, FULL_VERBATIM_INSTRUCTIONS):
        assert "unintelligible" in text.lower()


def test_seed_profiles_intact():
    assert [p["id"] for p in SEED_PROFILES] == ["full-verbatim", "clean-verbatim"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_seed_profiles.py -v`
Expected: FAIL — `test_both_prompts_have_italics_rule` (current prompts lack "italic").

- [ ] **Step 3: Write minimal implementation** — in `formatter/app/seed_profiles.py`, insert this paragraph into BOTH `CLEAN_VERBATIM_INSTRUCTIONS` and `FULL_VERBATIM_INSTRUCTIONS` immediately before the final `"Do not add speaker labels or timestamps."` line (keep everything else):

```
Italics: wrap in single asterisks (Markdown emphasis, *like this*) the titles of films, books, magazines, songs, artworks, plays, TV and radio programs, and any foreign-language expressions. Do NOT italicize social media sites, company names, or the Bible and its books.

Quotation marks are only for direct quotations and internal dialogue. Never put quotation marks around uncertain or unintelligible speech. You have no audio, so never invent [inaudible] or [unintelligible] tags; preserve any that are already in the input.
```

(The existing non-verbal/`[inaudible]` sentence in the source can remain; the new paragraph reinforces it and adds the italics rule. Ensure the word "unintelligible" appears in the added text for the test.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_seed_profiles.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/app/seed_profiles.py formatter/tests/test_seed_profiles.py
git commit -m "feat(formatter): add italics + quoting rules to seed prompts"
```

---

### Task 7: Wire new routes into the app

**Files:**
- Modify: `formatter/app/main.py`
- Test: `formatter/tests/test_segments_api.py` (new file — keeps these independent of v1's `test_api.py` helpers)

**Interfaces:**
- Consumes: `DiarizerClient` (Task 5), `format_segments` (Task 3), `exports.*` (Task 4), existing `ProfileStore`/`OllamaClient`/`Config`.
- Produces routes:
  - `POST /api/diarize` (multipart `audio`, optional form `num_speakers`) → segments JSON; `400` empty audio; `503` diarizer unreachable.
  - `POST /api/format/segments` (JSON `{segments, profile_id, model?, temperature?}`) → NDJSON stream of formatted turns; `400` empty segments; `404` unknown profile; `503`/`424` Ollama preflight (reuse v1 logic).
  - `POST /api/export` (JSON `{segments, format}`, format ∈ srt|vtt|txt|md) → rendered text with `Content-Disposition`; `400` unknown format.
- Adds `app.state.diarizer = DiarizerClient(config.diarizer_host)` and `get_diarizer` dependency.

- [ ] **Step 1: Write the failing test** — `formatter/tests/test_segments_api.py` (new file):

```python
import json

import httpx
from fastapi.testclient import TestClient

from app.config import Config
from app.diarizer_client import DiarizerClient
from app.main import create_app


def _cfg(tmp_path):
    return Config(
        ollama_host="http://ollama", model="m", temperature=0.2,
        max_chunk_words=800, profiles_dir=str(tmp_path), diarizer_host="http://diar:8090",
    )


class _OkOllama:
    def health(self):
        return {"reachable": True, "models": ["m"]}

    def chat(self, model, system, user, temperature):
        yield user.upper()


def _app(tmp_path, diar_handler):
    app = create_app(_cfg(tmp_path))
    app.state.client = _OkOllama()
    app.state.diarizer = DiarizerClient(
        "http://diar:8090", client=httpx.Client(transport=httpx.MockTransport(diar_handler))
    )
    return app


def test_diarize_route_proxies(tmp_path):
    def diar(request):
        return httpx.Response(200, json={"segments": [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "hi"}], "speakers": ["SPEAKER_00"], "language": "en"})

    client = TestClient(_app(tmp_path, diar))
    r = client.post("/api/diarize", files={"audio": ("a.wav", b"data", "audio/wav")})
    assert r.status_code == 200
    assert r.json()["speakers"] == ["SPEAKER_00"]


def test_diarize_route_empty_400(tmp_path):
    client = TestClient(_app(tmp_path, lambda req: httpx.Response(200, json={})))
    r = client.post("/api/diarize", files={"audio": ("a.wav", b"", "audio/wav")})
    assert r.status_code == 400


def test_format_segments_streams_ndjson(tmp_path):
    client = TestClient(_app(tmp_path, lambda req: httpx.Response(200, json={})))
    body = {
        "segments": [
            {"start": 0.0, "end": 1.0, "speaker": "A", "text": "hi"},
            {"start": 1.0, "end": 2.0, "speaker": "B", "text": "yo"},
        ],
        "profile_id": "clean-verbatim",
    }
    r = client.post("/api/format/segments", json=body)
    assert r.status_code == 200
    turns = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    assert [t["speaker"] for t in turns] == ["A", "B"]
    assert turns[0]["text"] == "HI"


def test_export_route_srt(tmp_path):
    client = TestClient(_app(tmp_path, lambda req: httpx.Response(200, json={})))
    body = {"format": "srt", "segments": [{"start": 0.0, "end": 1.0, "speaker": "A", "text": "hi"}]}
    r = client.post("/api/export", json=body)
    assert r.status_code == 200
    assert "00:00:00,000 --> 00:00:01,000" in r.text
    assert "A: hi" in r.text


def test_export_route_bad_format_400(tmp_path):
    client = TestClient(_app(tmp_path, lambda req: httpx.Response(200, json={})))
    r = client.post("/api/export", json={"format": "pdf", "segments": []})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_segments_api.py -v`
Expected: FAIL — new routes return 404 / attribute errors.

- [ ] **Step 3: Write minimal implementation** — in `formatter/app/main.py`:

Add imports near the top:
```python
import json as _json

from fastapi import File, Form, UploadFile

from app.diarizer_client import DiarizerClient, DiarizerUnreachable
from app.exports import to_markdown, to_srt, to_txt, to_vtt
from app.formatting import format_segments
```

Add request models beside the existing ones:
```python
class SegmentsFormatRequest(BaseModel):
    segments: list[dict]
    profile_id: str
    model: Optional[str] = None
    temperature: Optional[float] = None


class ExportRequest(BaseModel):
    segments: list[dict]
    format: str
```

In `create_app`, after `app.state.client = OllamaClient(config.ollama_host)`:
```python
    app.state.diarizer = DiarizerClient(config.diarizer_host)
```

Add a dependency near `get_client`:
```python
def get_diarizer(request: Request) -> DiarizerClient:
    return request.app.state.diarizer
```

Add the routes inside `create_app` (after the existing `/api/format` route):
```python
    @app.post("/api/diarize")
    async def diarize_route(
        audio: UploadFile = File(...),
        num_speakers: Optional[int] = Form(None),
        diarizer: DiarizerClient = Depends(get_diarizer),
        config: Config = Depends(get_config),
    ):
        data = await audio.read()
        if not data:
            raise HTTPException(400, "Audio file is empty.")
        try:
            return diarizer.diarize(data, audio.filename or "audio.wav", num_speakers)
        except DiarizerUnreachable:
            raise HTTPException(
                503,
                f"Diarizer isn't reachable at {config.diarizer_host}. "
                "Start it on the host (cd diarizer && ./run.sh).",
            )

    _EXPORTERS = {"srt": to_srt, "vtt": to_vtt, "txt": to_txt, "md": to_markdown}
    _EXPORT_MEDIA = {
        "srt": "application/x-subrip", "vtt": "text/vtt",
        "txt": "text/plain", "md": "text/markdown",
    }

    @app.post("/api/format/segments")
    def format_segments_route(
        req: SegmentsFormatRequest,
        store: ProfileStore = Depends(get_store),
        client: OllamaClient = Depends(get_client),
        config: Config = Depends(get_config),
    ):
        if not req.segments:
            raise HTTPException(400, "No segments to format.")
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
                424, f"Model '{resolved_model}' isn't installed. Run: ollama pull {resolved_model}"
            )

        def stream():
            for turn in format_segments(req.segments, profile, client, config):
                yield _json.dumps(turn) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/api/export")
    def export_route(req: ExportRequest):
        exporter = _EXPORTERS.get(req.format)
        if exporter is None:
            raise HTTPException(400, f"Unknown format '{req.format}'.")
        text = exporter(req.segments)
        return Response(
            content=text,
            media_type=_EXPORT_MEDIA[req.format],
            headers={"Content-Disposition": f'attachment; filename="transcript.{req.format}"'},
        )
```

Add `Response` to the FastAPI responses import at the top:
```python
from fastapi.responses import Response, StreamingResponse
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_segments_api.py -v`
Expected: PASS (5 new tests).

- [ ] **Step 5: Run the full suite**

Run: `cd formatter && python -m pytest -q`
Expected: PASS (all v1 tests + the new segment/export/diarizer/prompt tests).

- [ ] **Step 6: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add formatter/app/main.py formatter/tests/test_segments_api.py
git commit -m "feat(formatter): /api/diarize, /api/format/segments (NDJSON), /api/export"
```

---

### Task 8: Env, compose, and docs wiring

**Files:**
- Modify: `docker-compose.yml` (formatter service env), repo `.env`, `.env.example`, `README.md`

**Interfaces:** none (ops/docs). The formatter container reaches the host diarizer via `DIARIZER_HOST`.

- [ ] **Step 1: Add `DIARIZER_HOST` to the formatter service** in `docker-compose.yml`, under `formatter:` → `environment:` (it already has `extra_hosts: host.docker.internal:host-gateway`):

```yaml
      DIARIZER_HOST: ${DIARIZER_HOST:-http://host.docker.internal:8090}
```

- [ ] **Step 2: Append to repo `.env` and `.env.example`** (both), under the Transcript Formatter block:

```
# Host-native diarizer service (cd diarizer && ./run.sh). The formatter container
# reaches it over the host bridge.
DIARIZER_HOST=http://host.docker.internal:8090
```

- [ ] **Step 3: Update `README.md`** — in the Transcript Formatter section, add a sentence that speaker-labeled formatting requires the host-native diarizer (`diarizer/README.md`) running, reachable at `DIARIZER_HOST`.

- [ ] **Step 4: Verify the compose file parses**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
cd /Users/ekaranja/Code/speech-to-text
git add docker-compose.yml .env.example README.md
git commit -m "chore(formatter): wire DIARIZER_HOST into compose, env, and docs"
```

(Note: repo `.env` is git-ignored — edit it locally but it won't be staged.)

---

## Self-Review

- **Spec coverage:** diarizer proxy (Task 5 client + Task 7 route) ✓; segment-aware reflow preserving speaker/timestamps (Tasks 2–3) ✓; SRT/VTT/TXT/Markdown with italics + speaker labels (Task 4) ✓; italics + quoting prompt upgrades (Task 6) ✓; config + compose wiring (Tasks 1, 8) ✓; NDJSON streaming (Task 7) ✓. Additive — v1 routes/pages untouched. Frontend deferred to B2.
- **Placeholder scan:** none — every code step is complete; Task 6 quotes the exact paragraph to insert and where.
- **Type consistency:** segment dict keys `start/end/speaker/text` are identical across `group_turns`, `format_segments`, `exports.*`, `DiarizerClient` output, and every route/test. `format_segments` yields the same dict shape the exporters consume. `_model_available` and the Ollama preflight are reused verbatim from v1.
