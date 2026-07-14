from fastapi.testclient import TestClient

from app.config import DiarizerConfig
from app.main import create_app


def _cfg(token="hf_test"):
    return DiarizerConfig(
        port=8090, hf_token=token, whisper_model="medium",
        device="auto", model_cache="./cache",
    )


class FakeTranscriber:
    def transcribe(self, audio_path):
        return [{"start": 0.0, "end": 1.0, "word": " Hello"}], "en"


class FakeDiarizer:
    def diarize(self, audio_path, num_speakers):
        return [{"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"}]


def _client(token="hf_test"):
    app = create_app(_cfg(token), FakeTranscriber(), FakeDiarizer())
    return TestClient(app)


def test_health_ready_with_token():
    body = _client().get("/health").json()
    assert body["ready"] is True
    assert body["model"] == "medium"


def test_health_not_ready_without_token():
    assert _client(token=None).get("/health").json()["ready"] is False


def test_diarize_happy_path():
    r = _client().post("/diarize", files={"audio": ("a.wav", b"RIFFDATA", "audio/wav")})
    assert r.status_code == 200
    body = r.json()
    assert body["segments"][0]["speaker"] == "SPEAKER_00"
    assert body["segments"][0]["text"] == "Hello"
    assert body["speakers"] == ["SPEAKER_00"]
    assert body["language"] == "en"


def test_diarize_empty_audio_400():
    r = _client().post("/diarize", files={"audio": ("a.wav", b"", "audio/wav")})
    assert r.status_code == 400
