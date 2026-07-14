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
        return httpx.Response(
            200,
            json={"segments": [{"speaker": "SPEAKER_00"}], "speakers": ["SPEAKER_00"], "language": "en"},
        )

    result = _client(handler).diarize(b"audiobytes", "clip.wav")
    assert result["speakers"] == ["SPEAKER_00"]


def test_diarize_unreachable_raises():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(DiarizerUnreachable):
        _client(handler).diarize(b"x", "clip.wav")
