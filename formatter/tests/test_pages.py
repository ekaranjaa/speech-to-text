from app.config import load_config
from app.main import create_app


def _client(tmp_path):
    from fastapi.testclient import TestClient

    cfg = load_config({"FORMATTER_PROFILES_DIR": str(tmp_path)})
    return TestClient(create_app(cfg))


def test_manage_page_renders(tmp_path):
    resp = _client(tmp_path).get("/manage")
    assert resp.status_code == 200
    assert "/static/profiles.js" in resp.text


def test_root_is_spa_or_absent(tmp_path):
    # The SPA at "/" is only mounted when formatter/web/dist exists (built by
    # `npm run build` or the Docker build). In a bare env it's absent; either
    # way "/" must not error.
    resp = _client(tmp_path).get("/")
    assert resp.status_code in (200, 404)
