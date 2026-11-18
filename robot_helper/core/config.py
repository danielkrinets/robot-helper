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
