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
