import pytest

from matchmind import config


def test_missing_token_raises(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_a, **_k: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(config.MissingTokenError):
        config.load_settings()


def test_defaults_and_token_hidden(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_a, **_k: None)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret_value")
    monkeypatch.delenv("GITHUB_MODELS_ENDPOINT", raising=False)
    monkeypatch.delenv("GITHUB_MODELS_MODEL", raising=False)

    s = config.load_settings()

    assert s.endpoint == config.DEFAULT_ENDPOINT
    assert s.model == config.DEFAULT_MODEL
    assert "ghp_secret_value" not in repr(s)
