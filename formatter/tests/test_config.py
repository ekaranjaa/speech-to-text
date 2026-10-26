from app.config import Config, load_config


def test_defaults_applied_when_env_empty():
    cfg = load_config({})
    assert cfg.ollama_host == "http://host.docker.internal:11434"
    assert cfg.model == "qwen2.5:7b-instruct"
    assert cfg.temperature == 0.2
    assert cfg.max_chunk_words == 800
    assert cfg.profiles_dir == "/app/profiles"


def test_env_overrides():
    cfg = load_config(
        {
            "OLLAMA_HOST": "http://localhost:11434",
            "FORMATTER_MODEL": "qwen2.5:14b",
            "FORMATTER_TEMPERATURE": "0.5",
            "FORMATTER_MAX_CHUNK_WORDS": "500",
            "FORMATTER_PROFILES_DIR": "/tmp/profiles",
        }
    )
    assert cfg.ollama_host == "http://localhost:11434"
    assert cfg.model == "qwen2.5:14b"
    assert cfg.temperature == 0.5
    assert cfg.max_chunk_words == 500
    assert cfg.profiles_dir == "/tmp/profiles"


def test_config_is_frozen():
    cfg = load_config({})
    try:
        cfg.model = "other"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Config should be immutable")


def test_diarizer_host_default():
    assert load_config({}).diarizer_host == "http://host.docker.internal:8090"


def test_diarizer_host_override():
    cfg = load_config({"DIARIZER_HOST": "http://localhost:8090"})
    assert cfg.diarizer_host == "http://localhost:8090"
