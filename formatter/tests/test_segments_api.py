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
        return httpx.Response(
            200,
            json={
                "segments": [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "hi"}],
                "speakers": ["SPEAKER_00"],
                "language": "en",
            },
        )

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
