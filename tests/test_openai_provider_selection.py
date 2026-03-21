import importlib


def test_llmclient_selects_openai_provider(monkeypatch):
    monkeypatch.setenv("ACTIVE_MODEL", "OPENAI")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    # Reload config + client so they pick up env vars (ACTIVE_MODEL is read at import time).
    import src.config as config

    importlib.reload(config)

    import src.LLMAdaptor.client as client

    importlib.reload(client)

    c = client.LLMClient.from_config()
    assert getattr(c.provider, "name", None) == "OPENAI"
