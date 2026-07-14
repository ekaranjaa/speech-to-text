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
