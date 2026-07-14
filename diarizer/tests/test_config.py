from app.config import load_config


def test_defaults():
    cfg = load_config({})
    assert cfg.port == 8090
    assert cfg.hf_token is None
    assert cfg.whisper_model == "medium"
    assert cfg.device == "auto"
    assert cfg.model_cache == "../whishper_data/models"


def test_overrides():
    cfg = load_config({
        "DIARIZER_PORT": "9001",
        "HF_TOKEN": "hf_abc",
        "DIARIZER_WHISPER_MODEL": "large-v3",
        "DIARIZER_DEVICE": "cpu",
        "DIARIZER_MODEL_CACHE": "/models",
    })
    assert cfg.port == 9001
    assert cfg.hf_token == "hf_abc"
    assert cfg.whisper_model == "large-v3"
    assert cfg.device == "cpu"
    assert cfg.model_cache == "/models"


def test_blank_token_is_none():
    assert load_config({"HF_TOKEN": ""}).hf_token is None
