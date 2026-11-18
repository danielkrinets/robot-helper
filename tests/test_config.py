import keyring
import pytest

from robot_helper.core import config, texts


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_env_fallback(monkeypatch):
    monkeypatch.setattr(keyring, "get_password", lambda *a: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert config.get_api_key() == "from-env"


def test_keyring_wins(monkeypatch):
    monkeypatch.setattr(keyring, "get_password", lambda *a: "from-keyring")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert config.get_api_key() == "from-keyring"


def test_missing_returns_none(monkeypatch):
    monkeypatch.setattr(keyring, "get_password", lambda *a: None)
    assert config.get_api_key() is None


def test_keyring_failure_falls_back_to_env(monkeypatch):
    def boom(*a):
        raise keyring.errors.KeyringError("no backend")

    monkeypatch.setattr(keyring, "get_password", boom)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert config.get_api_key() == "from-env"


def test_set_api_key_stores_in_keyring(monkeypatch):
    calls = []
    monkeypatch.setattr(keyring, "set_password", lambda *a: calls.append(a))
    config.set_api_key("  secret  ")
    assert calls and calls[0][-1] == "secret"


def test_texts_have_no_forbidden_words():
    for value in texts.T.values():
        assert "нейросет" not in value.lower()
        assert "ИИ" not in value


def test_texts_have_required_keys():
    required = {"greeting", "press_to_talk", "thinking", "working", "waiting_you", "done",
                "stopped", "ask_yes", "ask_no", "stop", "no_key", "bad_key", "no_network",
                "try_again", "refused"}
    assert required <= set(texts.T)


def test_prefs_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PREFS", tmp_path / "prefs.json")
    assert config.get_pref("dock", "right") == "right"
    config.set_pref("dock", "left")
    assert config.get_pref("dock", "right") == "left"


def test_prefs_broken_file_gives_default(tmp_path, monkeypatch):
    bad = tmp_path / "prefs.json"
    bad.write_text("{not json")
    monkeypatch.setattr(config, "PREFS", bad)
    assert config.get_pref("dock", "right") == "right"
