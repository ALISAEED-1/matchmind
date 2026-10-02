import pytest

from matchmind import config

ENV_VARS = (
    "LLM_PROVIDER",
    "FOUNDRY_LOCAL_MODEL",
    "FOUNDRY_LOCAL_DEVICE",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_ENDPOINT",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_a, **_k: None)
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_to_foundry_local():
    s = config.load_settings()

    assert s.provider == "foundry_local"
    assert s.model == config.DEFAULT_FOUNDRY_MODEL
    assert s.foundry_device == "cpu"


def test_unknown_provider_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "github_models")
    with pytest.raises(config.ConfigError):
        config.load_settings()


def test_gemini_requires_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(config.ConfigError):
        config.load_settings()


def test_gemini_key_hidden_from_repr(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "secret_key_value")

    s = config.load_settings()

    assert s.provider == "gemini"
    assert s.model == config.DEFAULT_GEMINI_MODEL
    assert "secret_key_value" not in repr(s)
