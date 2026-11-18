"""API key storage: OS keychain first, ANTHROPIC_API_KEY env var as fallback."""
import os

import keyring

SERVICE = "robot-helper"
USER = "anthropic_api_key"


def get_api_key() -> str | None:
    try:
        key = keyring.get_password(SERVICE, USER)
    except keyring.errors.KeyringError:
        key = None
    return key or os.environ.get("ANTHROPIC_API_KEY") or None


def set_api_key(key: str) -> None:
    keyring.set_password(SERVICE, USER, key.strip())


# Non-secret UI preferences (dock position). Never store the API key here.
import json
import pathlib

PREFS = pathlib.Path.home() / ".robot-helper.json"


def _load() -> dict:
    try:
        return json.loads(PREFS.read_text())
    except (OSError, ValueError):
        return {}


def get_pref(name: str, default):
    return _load().get(name, default)


def set_pref(name: str, value) -> None:
    data = _load()
    data[name] = value
    try:
        PREFS.write_text(json.dumps(data))
    except OSError:
        pass
