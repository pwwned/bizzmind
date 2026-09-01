"""An env var that exists but is empty must read as unset — a hosting dashboard
makes that easy to do, and it silently picked the other AI backend."""
import importlib


def _backend(monkeypatch, value):
    import bizzmind.config as cfg
    if value is None:
        monkeypatch.delenv("AI_BACKEND", raising=False)
    else:
        monkeypatch.setenv("AI_BACKEND", value)
    monkeypatch.setattr(cfg, "_load_dotenv", lambda path: None)   # .env must not decide the test
    return importlib.reload(cfg).AI_BACKEND


def test_empty_backend_falls_back_to_the_default(monkeypatch):
    assert _backend(monkeypatch, "") == "subscription"
    assert _backend(monkeypatch, "   ") == "subscription"
    assert _backend(monkeypatch, None) == "subscription"


def test_explicit_backend_is_kept_and_trimmed(monkeypatch):
    assert _backend(monkeypatch, "api") == "api"
    assert _backend(monkeypatch, " api ") == "api"
