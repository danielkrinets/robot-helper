import sys

from robot_helper.platform_ import base
from robot_helper.platform_.macos import MacServices
from robot_helper.platform_.windows import WindowsServices, ps_quote


def test_get_platform_picks_by_sys_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert isinstance(base.get_platform(), WindowsServices)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert isinstance(base.get_platform(), MacServices)


def test_listen_returns_none():
    assert MacServices().listen() is None
    assert WindowsServices().listen() is None


def test_missing_permissions_is_list_of_strings(monkeypatch):
    svc = MacServices()
    monkeypatch.setattr(svc, "_accessibility_ok", lambda: False)
    monkeypatch.setattr(svc, "_screen_ok", lambda: True)
    missing = svc.missing_permissions()
    assert missing and all(isinstance(m, str) for m in missing)
    assert WindowsServices().missing_permissions() == []


def test_mac_speak_uses_russian_voice(monkeypatch):
    calls = []
    monkeypatch.setattr("subprocess.Popen", lambda args, **kw: calls.append(args))
    MacServices().speak("Привет")
    assert calls == [["say", "-v", "Milena", "Привет"]]


def test_powershell_quote_escapes_single_quotes():
    assert ps_quote("Маша's") == "'Маша''s'"


def test_dictation_hint_is_text():
    assert MacServices().dictation_hint() and WindowsServices().dictation_hint()
