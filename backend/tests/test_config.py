import pytest

from matchmind import config

ENV_VARS = (
    "LLM_CHAIN",
    "FOUNDRY_LOCAL_MODEL",
    "FOUNDRY_LOCAL_DEVICE",
    "GEMINI_API_KEY",
    "GEMINI_ENDPOINT",
    "LLM_TIMEOUT_S",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_a, **_k: None)
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_without_key_chain_is_foundry_local_only():
    s = config.load_settings()
    assert [p.name for p in s.chain] == ["foundry_local:qwen2.5-1.5b"]
    assert s.foundry_device == "cpu"


def test_with_key_chain_is_gemini_then_local(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret_key_value")
    s = config.load_settings()
    assert [p.kind for p in s.chain] == ["gemini", "gemini", "foundry_local"]
    assert "secret_key_value" not in repr(s)


def test_explicit_chain(monkeypatch):
    monkeypatch.setenv("LLM_CHAIN", "foundry_local:phi-4-mini, foundry_local:qwen2.5-1.5b")
    s = config.load_settings()
    assert [p.model for p in s.chain] == ["phi-4-mini", "qwen2.5-1.5b"]


@pytest.mark.parametrize("chain", ["github_models:gpt", "gemini", ","])
def test_bad_chain_rejected(monkeypatch, chain):
    monkeypatch.setenv("LLM_CHAIN", chain)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    with pytest.raises(config.ConfigError):
        config.load_settings()


def test_gemini_in_chain_requires_key(monkeypatch):
    monkeypatch.setenv("LLM_CHAIN", "gemini:gemini-3.5-flash")
    with pytest.raises(config.ConfigError):
        config.load_settings()
