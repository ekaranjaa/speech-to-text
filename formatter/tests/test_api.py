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
