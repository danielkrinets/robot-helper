import pytest

from robot_helper.core import config


@pytest.fixture(autouse=True)
def prefs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PREFS", tmp_path / "prefs.json")


def test_old_history_moves_into_first_chat():
    config.set_pref("history", [["привет", "me"], ["здравствуйте", "robot"]])
    from robot_helper.core.chats import Chats
    c = Chats()
    assert c.history == [("привет", "me"), ("здравствуйте", "robot")]


def test_new_switch_delete_and_title():
    from robot_helper.core.chats import Chats
    c = Chats()
    c.add("открой ютуб", "me")
    first = c.current_id
    assert c.current["title"] == "открой ютуб"
    c.new()
    assert c.current_id != first and c.history == []
    assert c.new()["id"] == c.current_id  # empty chat is reused
    c.switch(first)
    assert c.history[0][0] == "открой ютуб"
    c.delete(first)
    assert c.get(first) is None and c.current is not None
    assert Chats().current_id == c.current_id  # persisted


def test_notes_are_not_saved():
    from robot_helper.core.chats import Chats
    c = Chats()
    c.add("подсказка", "note")
    assert c.history == []
