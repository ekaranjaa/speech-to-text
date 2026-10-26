# Transcript Formatter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small self-hosted web app (`formatter`) that reflows a raw Whishper transcript into a chosen, saved style profile (e.g. GoTranscript clean/full verbatim) using a local Ollama model.

**Architecture:** A FastAPI app runs in a new Docker Compose service and serves a two-page UI. It stores editable style profiles as JSON files on a mounted volume and calls **Ollama running natively on the host** (`host.docker.internal:11434`, Metal GPU) for the LLM step. Long transcripts are split into chunks, each formatted with the profile's instructions as the system prompt, then re-joined and streamed to the browser.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, httpx (Ollama client + test transport), Jinja2 templates, vanilla JS (no build step), pytest. Ollama on the host runs the model (default `qwen2.5:7b-instruct`).

## Global Constraints

- **Python version:** 3.12 (container base `python:3.12-slim`).
- **Ollama stays on the host, never in Docker** — the container reaches it at `OLLAMA_HOST` (default `http://host.docker.internal:11434`); Compose service needs `extra_hosts: ["host.docker.internal:host-gateway"]`.
- **App listens on container port 8000**; the host port is `FORMATTER_PORT` (default `8084`) and is used only in the Compose `ports:` mapping — not by the app.
- **Default model:** `qwen2.5:7b-instruct`. **Default temperature:** `0.2`. **Default max chunk words:** `800`.
- **Profiles dir (in container):** `/app/profiles`, mounted from `./formatter_data/profiles`. Seed built-ins **only when the dir has no `.json` files** so user edits/deletions persist.
- **Reflow-only v1:** profiles must not add timestamps or speaker labels, and must not invent `[inaudible]`/`[unintelligible]` markers.
- **Run tests from the `formatter/` directory** with `python -m pytest` (puts `app` on the import path).
- **No content leaves the machine**; everything is local.

---

### Task 1: Project scaffold + config module

**Files:**
- Create: `formatter/requirements.txt`
- Create: `formatter/app/__init__.py`
- Create: `formatter/app/config.py`
- Test: `formatter/tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Config` frozen dataclass with fields: `ollama_host: str`, `model: str`, `temperature: float`, `max_chunk_words: int`, `profiles_dir: str`.
  - `load_config(env: Mapping[str, str] | None = None) -> Config` — reads env (defaults to `os.environ`), applies documented defaults.

- [ ] **Step 1: Create `formatter/requirements.txt`**

```
fastapi==0.115.6
uvicorn[standard]==0.32.1
httpx==0.28.1
jinja2==3.1.5
python-multipart==0.0.20
pytest==8.3.4
```

- [ ] **Step 2: Create `formatter/app/__init__.py`** (empty package marker)

```python
```

- [ ] **Step 3: Write the failing test** — `formatter/tests/test_config.py`

```python
from app.config import Config, load_config


def test_defaults_applied_when_env_empty():
    cfg = load_config({})
    assert cfg.ollama_host == "http://host.docker.internal:11434"
    assert cfg.model == "qwen2.5:7b-instruct"
    assert cfg.temperature == 0.2
    assert cfg.max_chunk_words == 800
    assert cfg.profiles_dir == "/app/profiles"


def test_env_overrides():
    cfg = load_config(
        {
            "OLLAMA_HOST": "http://localhost:11434",
            "FORMATTER_MODEL": "qwen2.5:14b",
            "FORMATTER_TEMPERATURE": "0.5",
            "FORMATTER_MAX_CHUNK_WORDS": "500",
            "FORMATTER_PROFILES_DIR": "/tmp/profiles",
        }
    )
    assert cfg.ollama_host == "http://localhost:11434"
    assert cfg.model == "qwen2.5:14b"
    assert cfg.temperature == 0.5
    assert cfg.max_chunk_words == 500
    assert cfg.profiles_dir == "/tmp/profiles"


def test_config_is_frozen():
    cfg = load_config({})
    try:
        cfg.model = "other"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Config should be immutable")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 5: Write minimal implementation** — `formatter/app/config.py`

```python
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


def load_config(env: Optional[Mapping[str, str]] = None) -> Config:
    e = os.environ if env is None else env
    return Config(
        ollama_host=e.get("OLLAMA_HOST", "http://host.docker.internal:11434"),
        model=e.get("FORMATTER_MODEL", "qwen2.5:7b-instruct"),
        temperature=float(e.get("FORMATTER_TEMPERATURE", "0.2")),
        max_chunk_words=int(e.get("FORMATTER_MAX_CHUNK_WORDS", "800")),
        profiles_dir=e.get("FORMATTER_PROFILES_DIR", "/app/profiles"),
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_config.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add formatter/requirements.txt formatter/app/__init__.py formatter/app/config.py formatter/tests/test_config.py
git commit -m "feat(formatter): project scaffold and config module"
```

---

### Task 2: Transcript chunking

**Files:**
- Create: `formatter/app/chunking.py`
- Test: `formatter/tests/test_chunking.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `split_transcript(text: str, max_words: int) -> list[str]` — splits on blank-line paragraphs, then sentences; greedily packs units so each chunk stays at/under `max_words` (a single unit longer than `max_words` becomes its own chunk). Empty/whitespace input returns `[]`.

- [ ] **Step 1: Write the failing test** — `formatter/tests/test_chunking.py`

```python
from app.chunking import split_transcript


def test_empty_returns_no_chunks():
    assert split_transcript("", 800) == []
    assert split_transcript("   \n\n  ", 800) == []


def test_short_text_is_single_chunk():
    assert split_transcript("Hello there friend.", 800) == ["Hello there friend."]


def test_two_small_paragraphs_pack_into_one_chunk():
    text = "one two three.\n\nfour five six."
    # max_words 800 -> both paragraphs fit in one chunk
    assert split_transcript(text, 800) == ["one two three.\n\nfour five six."]


def test_paragraphs_split_when_over_limit():
    text = "a a a.\n\nb b b.\n\nc c c."  # 3 paragraphs, 3 words each
    chunks = split_transcript(text, 4)  # only ~1 paragraph fits per chunk
    assert len(chunks) == 3
    assert chunks == ["a a a.", "b b b.", "c c c."]


def test_big_paragraph_splits_on_sentences():
    text = "one two three four. five six seven eight."  # 8 words, two sentences
    chunks = split_transcript(text, 5)
    assert chunks == ["one two three four.", "five six seven eight."]


def test_single_oversized_sentence_is_its_own_chunk():
    text = "word " * 10  # 10 words, one sentence, no terminal punctuation
    chunks = split_transcript(text.strip(), 3)
    assert len(chunks) == 1
    assert chunks[0].split() == ["word"] * 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_chunking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.chunking'`

- [ ] **Step 3: Write minimal implementation** — `formatter/app/chunking.py`

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_chunking.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add formatter/app/chunking.py formatter/tests/test_chunking.py
git commit -m "feat(formatter): transcript chunking"
```

---

### Task 3: Seed profiles + profile store

**Files:**
- Create: `formatter/app/seed_profiles.py`
- Create: `formatter/app/profiles.py`
- Test: `formatter/tests/test_profiles.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `SEED_PROFILES: list[dict]` — the two built-in profiles (`full-verbatim`, `clean-verbatim`), each `{id, name, description, instructions, model, temperature}`.
  - `ProfileStore(profiles_dir: str)` with: `seed_if_empty() -> None`, `list() -> list[dict]` (sorted by name), `get(profile_id: str) -> dict`, `create(data: dict) -> dict`, `update(profile_id: str, data: dict) -> dict`, `delete(profile_id: str) -> None`.
  - Exceptions: `ProfileError`, `ProfileNotFound(ProfileError)`, `DuplicateProfile(ProfileError)`.
  - `slugify(name: str) -> str`.

- [ ] **Step 1: Create the seed profiles** — `formatter/app/seed_profiles.py`

```python
CLEAN_VERBATIM_INSTRUCTIONS = """You are a professional transcript editor. You are given a raw, machine-generated transcript of spoken audio. Reformat it into GoTranscript-style clean verbatim. Never paraphrase, summarize, translate, reorder, or invent content — only reshape what is already present. Output only the edited transcript, with no preamble or commentary.

Remove: filler words (uh, um, you know, like, I mean, so, well, kind of, sort of) when they add no meaning; false starts; stutters; and repetitions — except repetitions used for emphasis ("No, no, no."; "very, very happy").

Keep interjections and expressions: Oh, Oh my God, Oh dear, Oh boy, et cetera. Do not remove "et cetera".

Convert: yeah/yep/yup/mm-hmm to "yes" when they answer a question (otherwise drop bare acknowledgements to keep the text fluent); expand slang — gonna to going to, wanna to want to, gotta to got to, gotcha to got you, 'cause to because; alright to all right; ok/OK to Okay.

Keep spoken contractions exactly (y'all, ain't, don't, it's). Do not correct grammatical errors. Do not use [sic]. Use correct spelling for misspoken words (e.g. "nitche" to "niche").

Punctuation and capitalization: capitalize the first word of every sentence; end every sentence with a punctuation mark, except a sentence left incomplete, which ends with a double dash -- (no spaces). Never use exclamation marks. Use -- for incomplete or interrupted sentences. Use double quotation marks for direct quotations and internal dialogue; commas and periods go inside the quotes.

Numbers: spell out zero to nine, use numerals for 10 and up; if a sentence mixes small and large numbers, use numerals for all. Money: $5, $1.5 million. Percentages: 100%. Years: '90s, 1990s. Times: 2:45 PM (capitalize AM/PM).

Abbreviations and acronyms: no periods (USA, PhD); research correct capitalization (iPhone, UCLA, SaaS).

Non-verbal sounds: only when clearly indicated in the source text, use lowercase bracket tags such as [laughs], [coughs], [crosstalk]. Never use parentheses for these. Do not invent [inaudible] or [unintelligible] tags or any timestamps — you have no audio. Preserve any bracketed tags already in the input.

Paragraphing: break long stretches into short paragraphs (about 100 words max), dividing where the meaning is clearest — often where the speaker links thoughts with "and", "so", or "but" — and drop those leading conjunctions when unnecessary.

Do not add speaker labels or timestamps."""

FULL_VERBATIM_INSTRUCTIONS = """You are a professional transcript editor. You are given a raw, machine-generated transcript of spoken audio. Reformat it into GoTranscript-style full verbatim. Transcribe everything as spoken — never paraphrase, summarize, translate, reorder, or invent content. Output only the edited transcript, with no preamble or commentary.

Keep everything: all filler words (um, uh, you know, kind of, sort of, I mean); false starts; stutters; repetitions; and slang written as spoken (kinda, gotta, wanna, dunno, gonna, 'cause). Keep affirmative and negative forms exactly (Mm-hmm, Uh-huh / Mm-mm, Uh-uh). Do not expand slang or remove anything.

Notation: use a single dash - (no spaces) for stutters ("m-m-moist") and repetitions ("why is this- why is this moist"). Use a double dash -- (no spaces) for false starts and speech errors ("I went on Tu-Thursday-- no, Friday.") and for incomplete or interrupted sentences.

Keep spoken contractions exactly. Do not correct grammatical errors. Do not use [sic]. Use correct spelling for misspoken words.

Punctuation and capitalization, numbers, abbreviations, and quotations: capitalize the first word of every sentence; end sentences with a punctuation mark except a trailing --; never use exclamation marks; spell out zero to nine and use numerals for 10 and up; no periods in acronyms (USA, PhD); use double quotation marks for direct and internal dialogue.

Non-verbal sounds: only when clearly indicated in the source text, use lowercase bracket tags (e.g. [laughs], [coughs], [crosstalk]); never parentheses. Do not invent [inaudible] or [unintelligible] tags or timestamps — you have no audio. Preserve bracketed tags already present.

Paragraphing: break long speeches into short paragraphs (about 100 words max) for readability, without changing any words.

Do not add speaker labels or timestamps."""

SEED_PROFILES = [
    {
        "id": "full-verbatim",
        "name": "Full Verbatim",
        "description": "GoTranscript-style full verbatim: keeps fillers, false starts, stutters, and repetitions exactly as spoken.",
        "instructions": FULL_VERBATIM_INSTRUCTIONS,
        "model": None,
        "temperature": None,
    },
    {
        "id": "clean-verbatim",
        "name": "Clean Verbatim",
        "description": "GoTranscript-style clean verbatim: removes fillers, false starts, and stutters while preserving meaning.",
        "instructions": CLEAN_VERBATIM_INSTRUCTIONS,
        "model": None,
        "temperature": None,
    },
]
```

- [ ] **Step 2: Write the failing test** — `formatter/tests/test_profiles.py`

```python
import pytest

from app.profiles import (
    DuplicateProfile,
    ProfileNotFound,
    ProfileStore,
    slugify,
)


def test_slugify():
    assert slugify("Clean Verbatim") == "clean-verbatim"
    assert slugify("  Legal  Style!! ") == "legal-style"


def test_seed_creates_two_profiles(tmp_path):
    store = ProfileStore(str(tmp_path))
    store.seed_if_empty()
    ids = sorted(p["id"] for p in store.list())
    assert ids == ["clean-verbatim", "full-verbatim"]


def test_seed_is_noop_when_not_empty(tmp_path):
    store = ProfileStore(str(tmp_path))
    store.create({"name": "Mine", "instructions": "do the thing"})
    store.seed_if_empty()
    assert [p["name"] for p in store.list()] == ["Mine"]


def test_create_and_get_roundtrip(tmp_path):
    store = ProfileStore(str(tmp_path))
    created = store.create({"name": "Legal Style", "instructions": "Format legally."})
    assert created["id"] == "legal-style"
    fetched = store.get("legal-style")
    assert fetched["instructions"] == "Format legally."
    assert fetched["model"] is None


def test_create_requires_name_and_instructions(tmp_path):
    store = ProfileStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.create({"name": "", "instructions": "x"})
    with pytest.raises(ValueError):
        store.create({"name": "x", "instructions": "  "})


def test_create_duplicate_raises(tmp_path):
    store = ProfileStore(str(tmp_path))
    store.create({"name": "Dup", "instructions": "a"})
    with pytest.raises(DuplicateProfile):
        store.create({"name": "Dup", "instructions": "b"})


def test_update_changes_fields(tmp_path):
    store = ProfileStore(str(tmp_path))
    store.create({"name": "Edit Me", "instructions": "old"})
    updated = store.update("edit-me", {"instructions": "new", "temperature": 0.4})
    assert updated["instructions"] == "new"
    assert updated["temperature"] == 0.4
    assert store.get("edit-me")["instructions"] == "new"


def test_get_missing_raises(tmp_path):
    store = ProfileStore(str(tmp_path))
    with pytest.raises(ProfileNotFound):
        store.get("nope")


def test_delete_removes(tmp_path):
    store = ProfileStore(str(tmp_path))
    store.create({"name": "Bye", "instructions": "x"})
    store.delete("bye")
    with pytest.raises(ProfileNotFound):
        store.get("bye")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_profiles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.profiles'`

- [ ] **Step 4: Write minimal implementation** — `formatter/app/profiles.py`

```python
from __future__ import annotations

import json
import re
from pathlib import Path

from app.seed_profiles import SEED_PROFILES

_ALLOWED_FIELDS = ("id", "name", "description", "instructions", "model", "temperature")


class ProfileError(Exception):
    pass


class ProfileNotFound(ProfileError):
    pass


class DuplicateProfile(ProfileError):
    pass


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug


class ProfileStore:
    def __init__(self, profiles_dir: str):
        self._dir = Path(profiles_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, profile_id: str) -> Path:
        return self._dir / f"{profile_id}.json"

    def _normalize(self, data: dict, profile_id: str) -> dict:
        return {
            "id": profile_id,
            "name": data["name"].strip(),
            "description": (data.get("description") or "").strip(),
            "instructions": data["instructions"].strip(),
            "model": data.get("model") or None,
            "temperature": data.get("temperature", None),
        }

    def _validate(self, data: dict) -> None:
        if not (data.get("name") or "").strip():
            raise ValueError("Profile name is required.")
        if not (data.get("instructions") or "").strip():
            raise ValueError("Profile instructions are required.")

    def seed_if_empty(self) -> None:
        if any(self._dir.glob("*.json")):
            return
        for profile in SEED_PROFILES:
            self._path(profile["id"]).write_text(
                json.dumps(profile, indent=2), encoding="utf-8"
            )

    def list(self) -> list[dict]:
        profiles = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in self._dir.glob("*.json")
        ]
        return sorted(profiles, key=lambda p: p["name"].lower())

    def get(self, profile_id: str) -> dict:
        path = self._path(profile_id)
        if not path.exists():
            raise ProfileNotFound(profile_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def create(self, data: dict) -> dict:
        self._validate(data)
        profile_id = (data.get("id") or slugify(data["name"])) or "profile"
        if self._path(profile_id).exists():
            raise DuplicateProfile(profile_id)
        profile = self._normalize(data, profile_id)
        self._path(profile_id).write_text(
            json.dumps(profile, indent=2), encoding="utf-8"
        )
        return profile

    def update(self, profile_id: str, data: dict) -> dict:
        existing = self.get(profile_id)
        merged = {**existing, **{k: v for k, v in data.items() if k in _ALLOWED_FIELDS}}
        self._validate(merged)
        profile = self._normalize(merged, profile_id)
        self._path(profile_id).write_text(
            json.dumps(profile, indent=2), encoding="utf-8"
        )
        return profile

    def delete(self, profile_id: str) -> None:
        path = self._path(profile_id)
        if not path.exists():
            raise ProfileNotFound(profile_id)
        path.unlink()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_profiles.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add formatter/app/seed_profiles.py formatter/app/profiles.py formatter/tests/test_profiles.py
git commit -m "feat(formatter): seed profiles and JSON profile store"
```

---

### Task 4: Ollama client

**Files:**
- Create: `formatter/app/ollama_client.py`
- Test: `formatter/tests/test_ollama_client.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `OllamaClient(host: str, timeout: float = 120.0, client: httpx.Client | None = None)`.
  - `.health() -> dict` → `{"reachable": bool, "models": list[str]}`.
  - `.chat(model: str, system: str, user: str, temperature: float) -> Iterator[str]` → yields content tokens.
  - Exceptions: `OllamaError`, `OllamaUnreachable(OllamaError)`, `ModelNotFound(OllamaError)`.

- [ ] **Step 1: Write the failing test** — `formatter/tests/test_ollama_client.py`

```python
import json

import httpx
import pytest

from app.ollama_client import ModelNotFound, OllamaClient


def _client_with(handler):
    transport = httpx.MockTransport(handler)
    return OllamaClient("http://ollama:11434", client=httpx.Client(transport=transport))


def test_health_reachable_lists_models():
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b-instruct"}]})

    health = _client_with(handler).health()
    assert health == {"reachable": True, "models": ["qwen2.5:7b-instruct"]}


def test_health_unreachable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    health = _client_with(handler).health()
    assert health == {"reachable": False, "models": []}


def test_chat_streams_tokens():
    body = (
        json.dumps({"message": {"content": "Hello"}, "done": False}) + "\n"
        + json.dumps({"message": {"content": " world"}, "done": True}) + "\n"
    )

    def handler(request):
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["options"]["temperature"] == 0.2
        return httpx.Response(200, content=body)

    tokens = list(_client_with(handler).chat("m", "sys", "usr", 0.2))
    assert "".join(tokens) == "Hello world"


def test_chat_model_not_found():
    def handler(request):
        return httpx.Response(404, json={"error": "model 'x' not found"})

    with pytest.raises(ModelNotFound):
        list(_client_with(handler).chat("x", "sys", "usr", 0.2))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_ollama_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ollama_client'`

- [ ] **Step 3: Write minimal implementation** — `formatter/app/ollama_client.py`

```python
from __future__ import annotations

import json
from typing import Iterator, Optional

import httpx


class OllamaError(Exception):
    pass


class OllamaUnreachable(OllamaError):
    pass


class ModelNotFound(OllamaError):
    pass


class OllamaClient:
    def __init__(
        self,
        host: str,
        timeout: float = 120.0,
        client: Optional[httpx.Client] = None,
    ):
        self._host = host.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def health(self) -> dict:
        try:
            resp = self._client.get(f"{self._host}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"reachable": True, "models": models}
        except (httpx.ConnectError, httpx.HTTPError):
            return {"reachable": False, "models": []}

    def chat(
        self, model: str, system: str, user: str, temperature: float
    ) -> Iterator[str]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": True,
            "options": {"temperature": temperature},
        }
        try:
            with self._client.stream(
                "POST", f"{self._host}/api/chat", json=payload
            ) as resp:
                if resp.status_code == 404:
                    resp.read()
                    raise ModelNotFound(model)
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    error = data.get("error")
                    if error:
                        if "not found" in error.lower():
                            raise ModelNotFound(model)
                        raise OllamaError(error)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done"):
                        break
        except httpx.ConnectError as exc:
            raise OllamaUnreachable(str(exc)) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_ollama_client.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add formatter/app/ollama_client.py formatter/tests/test_ollama_client.py
git commit -m "feat(formatter): streaming Ollama client with error mapping"
```

---

### Task 5: Formatting engine

**Files:**
- Create: `formatter/app/formatting.py`
- Test: `formatter/tests/test_formatting.py`

**Interfaces:**
- Consumes: `split_transcript` (Task 2), `Config` (Task 1), an object with `.chat(model, system, user, temperature) -> Iterator[str]` (Task 4 shape).
- Produces: `format_transcript(text: str, profile: dict, client, config: Config) -> Iterator[str]` — resolves model/temperature (profile overrides win over config), chunks the text, formats each chunk, joins chunks with a blank line, streams tokens.

- [ ] **Step 1: Write the failing test** — `formatter/tests/test_formatting.py`

```python
from app.config import load_config
from app.formatting import format_transcript


class FakeClient:
    def __init__(self):
        self.calls = []

    def chat(self, model, system, user, temperature):
        self.calls.append({"model": model, "temperature": temperature, "user": user})
        yield user.upper()


def _profile(**overrides):
    base = {
        "id": "p",
        "name": "P",
        "instructions": "SYS",
        "model": None,
        "temperature": None,
    }
    base.update(overrides)
    return base


def test_single_chunk_uses_config_defaults():
    cfg = load_config({})
    client = FakeClient()
    out = "".join(format_transcript("hello world.", _profile(), client, cfg))
    assert out == "HELLO WORLD."
    assert client.calls[0]["model"] == "qwen2.5:7b-instruct"
    assert client.calls[0]["temperature"] == 0.2


def test_multiple_chunks_joined_with_blank_line():
    cfg = load_config({"FORMATTER_MAX_CHUNK_WORDS": "2"})
    client = FakeClient()
    out = "".join(format_transcript("a a.\n\nb b.", _profile(), client, cfg))
    assert out == "A A.\n\nB B."
    assert len(client.calls) == 2


def test_profile_overrides_win():
    cfg = load_config({})
    client = FakeClient()
    list(format_transcript("x.", _profile(model="qwen2.5:14b", temperature=0.7), client, cfg))
    assert client.calls[0]["model"] == "qwen2.5:14b"
    assert client.calls[0]["temperature"] == 0.7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_formatting.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.formatting'`

- [ ] **Step 3: Write minimal implementation** — `formatter/app/formatting.py`

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_formatting.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add formatter/app/formatting.py formatter/tests/test_formatting.py
git commit -m "feat(formatter): formatting engine orchestrating chunk -> Ollama -> join"
```

---

### Task 6: FastAPI app factory + JSON API

**Files:**
- Create: `formatter/app/main.py`
- Test: `formatter/tests/test_api.py`

**Interfaces:**
- Consumes: `load_config`/`Config` (Task 1), `ProfileStore` + exceptions (Task 3), `OllamaClient` (Task 4), `format_transcript` (Task 5).
- Produces:
  - `create_app(config: Config | None = None) -> FastAPI` — seeds profiles on startup, stores `config`/`store`/`client` on `app.state`.
  - Dependency providers `get_config`, `get_store`, `get_client` (overridable in tests).
  - `_model_available(model: str, available: list[str]) -> bool`.
  - No module-level app instance — uvicorn runs it via the factory (`--factory app.main:create_app`) so importing `app.main` has no filesystem side effects.
  - JSON routes: `GET /api/health`, `GET/POST /api/profiles`, `GET/PUT/DELETE /api/profiles/{id}`, `POST /api/format` (streaming `text/plain`).

- [ ] **Step 1: Write the failing test** — `formatter/tests/test_api.py`

```python
import pytest
from fastapi.testclient import TestClient

from app.config import load_config
from app.main import create_app, get_client


class FakeClient:
    def __init__(self, reachable=True, models=None):
        self._reachable = reachable
        self._models = models or ["qwen2.5:7b-instruct"]

    def health(self):
        return {"reachable": self._reachable, "models": self._models}

    def chat(self, model, system, user, temperature):
        yield f"[{user.strip()}]"


@pytest.fixture
def client(tmp_path):
    cfg = load_config({"FORMATTER_PROFILES_DIR": str(tmp_path)})
    app = create_app(cfg)
    app.dependency_overrides[get_client] = lambda: FakeClient()
    return TestClient(app), app


def test_health(client):
    tc, _ = client
    assert tc.get("/api/health").json() == {
        "reachable": True,
        "models": ["qwen2.5:7b-instruct"],
    }


def test_seeded_profiles_listed(client):
    tc, _ = client
    ids = sorted(p["id"] for p in tc.get("/api/profiles").json())
    assert ids == ["clean-verbatim", "full-verbatim"]


def test_profile_crud(client):
    tc, _ = client
    created = tc.post("/api/profiles", json={"name": "Mine", "instructions": "do"}).json()
    assert created["id"] == "mine"
    tc.put("/api/profiles/mine", json={"instructions": "do better"})
    assert tc.get("/api/profiles/mine").json()["instructions"] == "do better"
    assert tc.delete("/api/profiles/mine").status_code == 204
    assert tc.get("/api/profiles/mine").status_code == 404


def test_duplicate_profile_conflicts(client):
    tc, _ = client
    tc.post("/api/profiles", json={"name": "Dup", "instructions": "a"})
    assert tc.post("/api/profiles", json={"name": "Dup", "instructions": "b"}).status_code == 409


def test_format_streams_result(client):
    tc, _ = client
    resp = tc.post("/api/format", json={"text": "hello.", "profile_id": "clean-verbatim"})
    assert resp.status_code == 200
    assert resp.text == "[hello.]"


def test_format_empty_text_rejected(client):
    tc, _ = client
    assert tc.post("/api/format", json={"text": "  ", "profile_id": "clean-verbatim"}).status_code == 400


def test_format_ollama_unreachable(tmp_path):
    cfg = load_config({"FORMATTER_PROFILES_DIR": str(tmp_path)})
    app = create_app(cfg)
    app.dependency_overrides[get_client] = lambda: FakeClient(reachable=False, models=[])
    tc = TestClient(app)
    resp = tc.post("/api/format", json={"text": "hi.", "profile_id": "clean-verbatim"})
    assert resp.status_code == 503


def test_format_model_not_installed(tmp_path):
    cfg = load_config({"FORMATTER_PROFILES_DIR": str(tmp_path)})
    app = create_app(cfg)
    app.dependency_overrides[get_client] = lambda: FakeClient(models=["other:latest"])
    tc = TestClient(app)
    resp = tc.post("/api/format", json={"text": "hi.", "profile_id": "clean-verbatim"})
    assert resp.status_code == 424
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd formatter && python -m pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Write minimal implementation** — `formatter/app/main.py`

```python
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import Config, load_config
from app.formatting import format_transcript
from app.ollama_client import OllamaClient
from app.profiles import DuplicateProfile, ProfileNotFound, ProfileStore

_APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_APP_DIR / "templates"))


class ProfileBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None


class FormatRequest(BaseModel):
    text: str
    profile_id: str
    model: Optional[str] = None
    temperature: Optional[float] = None


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_store(request: Request) -> ProfileStore:
    return request.app.state.store


def get_client(request: Request) -> OllamaClient:
    return request.app.state.client


def _model_available(model: str, available: list[str]) -> bool:
    if model in available:
        return True
    base = model.split(":")[0]
    return any(a == base or a.split(":")[0] == base for a in available)


def create_app(config: Optional[Config] = None) -> FastAPI:
    config = config or load_config()
    app = FastAPI(title="Transcript Formatter")

    store = ProfileStore(config.profiles_dir)
    store.seed_if_empty()

    app.state.config = config
    app.state.store = store
    app.state.client = OllamaClient(config.ollama_host)

    (_APP_DIR / "templates").mkdir(parents=True, exist_ok=True)
    static_dir = _APP_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/api/health")
    def health(client: OllamaClient = Depends(get_client)):
        return client.health()

    @app.get("/api/profiles")
    def list_profiles(store: ProfileStore = Depends(get_store)):
        return store.list()

    @app.get("/api/profiles/{profile_id}")
    def get_profile(profile_id: str, store: ProfileStore = Depends(get_store)):
        try:
            return store.get(profile_id)
        except ProfileNotFound:
            raise HTTPException(404, f"Profile '{profile_id}' not found.")

    @app.post("/api/profiles", status_code=201)
    def create_profile(body: ProfileBody, store: ProfileStore = Depends(get_store)):
        try:
            return store.create(body.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except DuplicateProfile:
            raise HTTPException(409, "A profile with that name already exists.")

    @app.put("/api/profiles/{profile_id}")
    def update_profile(
        profile_id: str, body: ProfileBody, store: ProfileStore = Depends(get_store)
    ):
        try:
            return store.update(profile_id, body.model_dump(exclude_none=True))
        except ProfileNotFound:
            raise HTTPException(404, f"Profile '{profile_id}' not found.")
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.delete("/api/profiles/{profile_id}", status_code=204)
    def delete_profile(profile_id: str, store: ProfileStore = Depends(get_store)):
        try:
            store.delete(profile_id)
        except ProfileNotFound:
            raise HTTPException(404, f"Profile '{profile_id}' not found.")

    @app.post("/api/format")
    def format_route(
        req: FormatRequest,
        store: ProfileStore = Depends(get_store),
        client: OllamaClient = Depends(get_client),
        config: Config = Depends(get_config),
    ):
        if not req.text.strip():
            raise HTTPException(400, "Transcript text is empty.")
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
                424,
                f"Model '{resolved_model}' isn't installed. "
                f"Run: ollama pull {resolved_model}",
            )

        stream = format_transcript(req.text, profile, client, config)
        return StreamingResponse(stream, media_type="text/plain; charset=utf-8")

    @app.get("/")
    def format_page(request: Request, store: ProfileStore = Depends(get_store)):
        return templates.TemplateResponse(
            "format.html", {"request": request, "profiles": store.list()}
        )

    @app.get("/manage")
    def manage_page(request: Request):
        return templates.TemplateResponse("profiles.html", {"request": request})

    return app
```

> Note: there is intentionally **no** module-level `app = create_app()` — uvicorn
> instantiates it via `--factory` (see Task 8), so importing `app.main` never
> touches the filesystem (which would fail on a host without a writable `/app`).
>
> Note: `GET /` and `GET /manage` reference templates created in Task 7. They are wired here but exercised by Task 7's tests.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_api.py -v`
Expected: PASS (8 tests). (The page routes are not hit by these tests.)

- [ ] **Step 5: Commit**

```bash
git add formatter/app/main.py formatter/tests/test_api.py
git commit -m "feat(formatter): FastAPI app factory and JSON API"
```

---

### Task 7: Web UI (templates, static assets, page routes)

**Files:**
- Create: `formatter/app/templates/base.html`
- Create: `formatter/app/templates/format.html`
- Create: `formatter/app/templates/profiles.html`
- Create: `formatter/app/static/style.css`
- Create: `formatter/app/static/format.js`
- Create: `formatter/app/static/profiles.js`
- Test: `formatter/tests/test_pages.py`

**Interfaces:**
- Consumes: page routes `GET /` and `GET /manage` and the JSON API from Task 6.
- Produces: rendered HTML pages; a `format.js` that streams `POST /api/format` into an output box with copy/download, and a `profiles.js` that does profile CRUD against `/api/profiles`.

- [ ] **Step 1: Create `formatter/app/templates/base.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Transcript Formatter{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <h1>Transcript Formatter</h1>
    <nav>
      <a href="/">Format</a>
      <a href="/manage">Profiles</a>
    </nav>
  </header>
  <main>
    {% block content %}{% endblock %}
  </main>
  {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Create `formatter/app/templates/format.html`**

```html
{% extends "base.html" %}
{% block content %}
<section class="grid">
  <div>
    <label for="profile">Style profile</label>
    <select id="profile">
      {% for p in profiles %}
      <option value="{{ p.id }}">{{ p.name }}</option>
      {% endfor %}
    </select>
    <label for="input">Transcript</label>
    <textarea id="input" rows="18" placeholder="Paste a transcript, or upload a .txt file below."></textarea>
    <input type="file" id="file" accept=".txt,text/plain">
    <button id="run">Format</button>
    <p id="status" class="status"></p>
  </div>
  <div>
    <label for="output">Formatted output</label>
    <textarea id="output" rows="18" readonly></textarea>
    <button id="copy">Copy</button>
    <button id="download">Download .txt</button>
  </div>
</section>
{% endblock %}
{% block scripts %}<script src="/static/format.js"></script>{% endblock %}
```

- [ ] **Step 3: Create `formatter/app/templates/profiles.html`**

```html
{% extends "base.html" %}
{% block content %}
<section class="grid">
  <div>
    <h2>Profiles</h2>
    <ul id="list"></ul>
    <button id="new">New profile</button>
  </div>
  <div>
    <h2 id="editor-title">Editor</h2>
    <input type="hidden" id="edit-id">
    <label for="name">Name</label>
    <input type="text" id="name">
    <label for="description">Description</label>
    <input type="text" id="description">
    <label for="instructions">Instructions (system prompt)</label>
    <textarea id="instructions" rows="14"></textarea>
    <label for="model">Model override (optional)</label>
    <input type="text" id="model" placeholder="e.g. qwen2.5:14b">
    <label for="temperature">Temperature override (optional)</label>
    <input type="number" id="temperature" step="0.1" min="0" max="2">
    <div class="row">
      <button id="save">Save</button>
      <button id="delete">Delete</button>
    </div>
    <p id="status" class="status"></p>
  </div>
</section>
{% endblock %}
{% block scripts %}<script src="/static/profiles.js"></script>{% endblock %}
```

- [ ] **Step 4: Create `formatter/app/static/style.css`**

```css
:root { font-family: system-ui, sans-serif; }
body { margin: 0; color: #1a1a1a; }
header { display: flex; align-items: baseline; gap: 1.5rem; padding: 1rem 1.5rem; border-bottom: 1px solid #ddd; }
header h1 { font-size: 1.15rem; margin: 0; }
nav a { margin-right: 1rem; text-decoration: none; color: #2563eb; }
main { padding: 1.5rem; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
label { display: block; margin: 0.75rem 0 0.25rem; font-weight: 600; font-size: 0.9rem; }
textarea, input, select { width: 100%; box-sizing: border-box; padding: 0.5rem; font: inherit; }
textarea { resize: vertical; font-family: ui-monospace, monospace; }
button { margin-top: 0.75rem; margin-right: 0.5rem; padding: 0.5rem 1rem; cursor: pointer; }
.status { min-height: 1.2rem; color: #b45309; }
.row { display: flex; }
ul#list { list-style: none; padding: 0; }
ul#list li { padding: 0.4rem 0; cursor: pointer; color: #2563eb; }
@media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
```

- [ ] **Step 5: Create `formatter/app/static/format.js`**

```javascript
const $ = (id) => document.getElementById(id);

$("file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (file) $("input").value = await file.text();
});

$("run").addEventListener("click", async () => {
  const text = $("input").value;
  const profile_id = $("profile").value;
  if (!text.trim()) { $("status").textContent = "Paste or upload a transcript first."; return; }
  $("output").value = "";
  $("status").textContent = "Formatting…";
  $("run").disabled = true;
  try {
    const resp = await fetch("/api/format", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, profile_id }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      $("status").textContent = "Error: " + (err.detail || resp.statusText);
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      $("output").value += decoder.decode(value, { stream: true });
    }
    $("status").textContent = "Done.";
  } catch (e) {
    $("status").textContent = "Error: " + e.message;
  } finally {
    $("run").disabled = false;
  }
});

$("copy").addEventListener("click", () => navigator.clipboard.writeText($("output").value));

$("download").addEventListener("click", () => {
  const blob = new Blob([$("output").value], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "formatted-transcript.txt";
  a.click();
  URL.revokeObjectURL(a.href);
});
```

- [ ] **Step 6: Create `formatter/app/static/profiles.js`**

```javascript
const $ = (id) => document.getElementById(id);
let editingExisting = false;

async function refresh() {
  const profiles = await (await fetch("/api/profiles")).json();
  const list = $("list");
  list.innerHTML = "";
  for (const p of profiles) {
    const li = document.createElement("li");
    li.textContent = p.name;
    li.addEventListener("click", () => load(p.id));
    list.appendChild(li);
  }
}

async function load(id) {
  const p = await (await fetch("/api/profiles/" + id)).json();
  editingExisting = true;
  $("edit-id").value = p.id;
  $("name").value = p.name;
  $("description").value = p.description || "";
  $("instructions").value = p.instructions;
  $("model").value = p.model || "";
  $("temperature").value = p.temperature ?? "";
  $("editor-title").textContent = "Editing: " + p.name;
  $("status").textContent = "";
}

function blank() {
  editingExisting = false;
  ["edit-id", "name", "description", "instructions", "model", "temperature"].forEach((k) => ($(k).value = ""));
  $("editor-title").textContent = "New profile";
  $("status").textContent = "";
}

function payload() {
  const body = {
    name: $("name").value,
    description: $("description").value,
    instructions: $("instructions").value,
  };
  if ($("model").value.trim()) body.model = $("model").value.trim();
  if ($("temperature").value !== "") body.temperature = parseFloat($("temperature").value);
  return body;
}

$("new").addEventListener("click", blank);

$("save").addEventListener("click", async () => {
  const id = $("edit-id").value;
  const url = editingExisting ? "/api/profiles/" + id : "/api/profiles";
  const method = editingExisting ? "PUT" : "POST";
  const resp = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload()),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    $("status").textContent = "Error: " + (err.detail || resp.statusText);
    return;
  }
  await refresh();
  const saved = await resp.json();
  await load(saved.id);
  $("status").textContent = "Saved.";
});

$("delete").addEventListener("click", async () => {
  const id = $("edit-id").value;
  if (!id) return;
  await fetch("/api/profiles/" + id, { method: "DELETE" });
  blank();
  await refresh();
});

refresh();
```

- [ ] **Step 7: Write the failing test** — `formatter/tests/test_pages.py`

```python
from fastapi.testclient import TestClient

from app.config import load_config
from app.main import create_app


def _client(tmp_path):
    cfg = load_config({"FORMATTER_PROFILES_DIR": str(tmp_path)})
    return TestClient(create_app(cfg))


def test_format_page_lists_seeded_profiles(tmp_path):
    resp = _client(tmp_path).get("/")
    assert resp.status_code == 200
    assert "Clean Verbatim" in resp.text
    assert "Full Verbatim" in resp.text
    assert "/static/format.js" in resp.text


def test_manage_page_renders(tmp_path):
    resp = _client(tmp_path).get("/manage")
    assert resp.status_code == 200
    assert "/static/profiles.js" in resp.text
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd formatter && python -m pytest tests/test_pages.py -v`
Expected: PASS (2 tests). (Templates and static dir now exist, so `create_app` renders them.)

- [ ] **Step 9: Run the full suite**

Run: `cd formatter && python -m pytest -v`
Expected: PASS (all tasks' tests green).

- [ ] **Step 10: Commit**

```bash
git add formatter/app/templates formatter/app/static formatter/tests/test_pages.py
git commit -m "feat(formatter): web UI pages, static assets, and page tests"
```

---

### Task 8: Dockerize, wire into Compose, config, docs

**Files:**
- Create: `formatter/Dockerfile`
- Create: `formatter/.dockerignore`
- Modify: `docker-compose.yml` (add `formatter` service)
- Modify: `.env` and `.env.example` (add `FORMATTER_*` / `OLLAMA_HOST` vars)
- Modify: `.gitignore` (add `formatter_data/`)
- Modify: `README.md` (add Formatter section)

**Interfaces:**
- Consumes: the app from Tasks 1–7.
- Produces: a running `formatter` container reachable at `http://localhost:8084`, talking to host Ollama.

- [ ] **Step 1: Create `formatter/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `formatter/.dockerignore`**

```
tests/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: Add the `formatter` service to `docker-compose.yml`**

Append this service under `services:` (sibling of `whishper`):

```yaml
  # Transcript Formatter — local LLM post-processing. Reflows a Whishper
  # transcript into a saved style profile (GoTranscript-style clean/full
  # verbatim, etc.) via Ollama running NATIVELY on the host (Metal GPU).
  # Ollama is deliberately NOT containerized: Docker on macOS has no GPU
  # passthrough, so an in-container model would be CPU-only and slow.
  formatter:
    build: ./formatter
    container_name: whishper-formatter
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - ${FORMATTER_PORT:-8084}:8000
    volumes:
      - ./formatter_data/profiles:/app/profiles
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      OLLAMA_HOST: ${OLLAMA_HOST:-http://host.docker.internal:11434}
      FORMATTER_MODEL: ${FORMATTER_MODEL:-qwen2.5:7b-instruct}
      FORMATTER_TEMPERATURE: ${FORMATTER_TEMPERATURE:-0.2}
      FORMATTER_MAX_CHUNK_WORDS: ${FORMATTER_MAX_CHUNK_WORDS:-800}
```

- [ ] **Step 4: Append formatter vars to `.env.example`** (and mirror into `.env`)

Add to the end of the repo-root `.env.example`:

```
# --- Transcript Formatter (local LLM post-processing) ---
# Host port for the formatter UI (container listens on 8000 internally).
FORMATTER_PORT=8084
# Ollama runs natively on the host; the container reaches it here.
OLLAMA_HOST=http://host.docker.internal:11434
# Default Ollama model. On a 16 GB M1 Pro, a 7B model is the comfortable
# default; bump to qwen2.5:14b when you're not transcribing at the same time.
FORMATTER_MODEL=qwen2.5:7b-instruct
FORMATTER_TEMPERATURE=0.2
FORMATTER_MAX_CHUNK_WORDS=800
```

Then copy the same block into your local `.env` (git-ignored):

```bash
cat >> .env <<'EOF'

# --- Transcript Formatter (local LLM post-processing) ---
FORMATTER_PORT=8084
OLLAMA_HOST=http://host.docker.internal:11434
FORMATTER_MODEL=qwen2.5:7b-instruct
FORMATTER_TEMPERATURE=0.2
FORMATTER_MAX_CHUNK_WORDS=800
EOF
```

- [ ] **Step 5: Add `formatter_data/` to `.gitignore`**

Insert after the `whishper_data/` block:

```
# Formatter profiles (editable style profiles) — machine-local.
formatter_data/
```

- [ ] **Step 6: Add a Formatter section to `README.md`**

Add this after the Stack table (adjust wording to match surrounding tone):

```markdown
## Transcript Formatter (optional post-processing)

A fourth service, **`formatter`** (http://localhost:8084), reflows a raw
transcript into a saved **style profile** (e.g. GoTranscript-style clean or full
verbatim) using a **local LLM**. Export a transcript from Whishper, paste or
upload it, pick a profile, and copy/download the formatted result.

**Prerequisite — Ollama on the host** (not in Docker, so it uses the Metal GPU):

```bash
brew install ollama        # if not already installed
ollama serve &             # or launch the Ollama app
ollama pull qwen2.5:7b-instruct
```

Then `docker compose up -d --build` and open http://localhost:8084.

> Like Whishper's first run, the first format call fails clearly if Ollama isn't
> running or the model isn't pulled — the UI tells you which and how to fix it.

Profiles are editable in the **Profiles** tab and persist under
`./formatter_data/profiles/` (git-ignored). Two are seeded on first run: **Full
Verbatim** and **Clean Verbatim**.
```

- [ ] **Step 7: Build and start the service**

Run: `docker compose up -d --build formatter`
Expected: image builds, `whishper-formatter` starts.

- [ ] **Step 8: Verify health (Ollama running + model pulled)**

Run: `curl -s http://localhost:8084/api/health`
Expected: `{"reachable":true,"models":[...]}` including `qwen2.5:7b-instruct`.
If `reachable` is false, start Ollama on the host; if the model is missing, `ollama pull qwen2.5:7b-instruct`.

- [ ] **Step 9: Manual end-to-end**

1. Open http://localhost:8084.
2. Paste a short raw transcript (with some "um"s and false starts), pick **Clean Verbatim**, click **Format**. Confirm fillers/false starts are removed and output streams in.
3. Switch to **Full Verbatim**, format the same text. Confirm fillers are kept.
4. Open **Profiles**, edit Clean Verbatim's description, Save, reload — confirm the change persisted.

- [ ] **Step 10: Commit**

```bash
git add formatter/Dockerfile formatter/.dockerignore docker-compose.yml .env.example .gitignore README.md
git commit -m "feat(formatter): dockerize, wire into compose, env, and docs"
```

---

## Notes for the implementer

- **Import style:** modules import as `from app.xxx import ...`; always run pytest from the `formatter/` directory (`cd formatter && python -m pytest`).
- **Do not** run Ollama inside Docker on macOS — it would be CPU-only. The container calls the host's Ollama.
- **Streaming:** `POST /api/format` returns `text/plain` streamed; the pre-flight health check makes error cases (Ollama down, model missing) return clean HTTP errors *before* streaming starts.
- **Profiles persistence:** seeding only happens when the profiles dir has no `*.json`, so user edits/deletes are never overwritten on restart.
