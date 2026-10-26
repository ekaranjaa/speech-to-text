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
