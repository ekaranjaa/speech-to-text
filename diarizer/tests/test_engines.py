import pytest

from app.config import DiarizerConfig
from app.engines import DiarizerConfigError, build_real_engines, resolve_device


class _FakeMPS:
    def __init__(self, available):
        self._available = available

    def is_available(self):
        return self._available


class _FakeBackends:
    def __init__(self, mps_available):
        self.mps = _FakeMPS(mps_available)


class _FakeTorch:
    def __init__(self, mps_available):
        self.backends = _FakeBackends(mps_available)


def test_resolve_device_auto_prefers_mps():
    assert resolve_device("auto", _FakeTorch(True)) == "mps"


def test_resolve_device_auto_falls_back_to_cpu():
    assert resolve_device("auto", _FakeTorch(False)) == "cpu"


def test_resolve_device_explicit_passthrough():
    assert resolve_device("cpu", _FakeTorch(True)) == "cpu"
    assert resolve_device("cuda", _FakeTorch(False)) == "cuda"


def test_build_real_engines_requires_token():
    cfg = DiarizerConfig(
        port=8090, hf_token=None, whisper_model="medium",
        device="auto", model_cache="./cache",
    )
    with pytest.raises(DiarizerConfigError):
        build_real_engines(cfg)
