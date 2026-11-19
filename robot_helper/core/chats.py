"""Several saved conversations, like in any chat app. Stored in the prefs file."""
from __future__ import annotations

import time
import uuid

from robot_helper.core import config

KEEP_MESSAGES = 200
KEEP_CHATS = 50


class Chats:
    def __init__(self):
        self.items: list[dict] = config.get_pref("chats", [])
        old = config.get_pref("history", [])
        if not self.items and old:  # one-time move of the single old history into the first chat
            self.items = [self._new(old)]
        self.current_id = config.get_pref("current_chat", "")
        if not self.items:
            self.items = [self._new()]
        if self.get(self.current_id) is None:
            self.current_id = self.items[0]["id"]
        self.save()

    @staticmethod
    def _new(history=None) -> dict:
        return {"id": uuid.uuid4().hex[:12], "title": "", "updated": time.time(), "history": list(history or [])}

    def get(self, chat_id: str) -> dict | None:
        return next((c for c in self.items if c["id"] == chat_id), None)

    @property
    def current(self) -> dict:
        return self.get(self.current_id)

    @property
    def history(self) -> list[tuple[str, str]]:
        return [tuple(x) for x in self.current["history"]]

    def add(self, text: str, who: str) -> None:
        if who == "note":
            return
        chat = self.current
        chat["history"] = (chat["history"] + [[text, who]])[-KEEP_MESSAGES:]
        if not chat["title"] and who == "me":
            chat["title"] = text.strip().splitlines()[0][:40]
        chat["updated"] = time.time()
        self.items.sort(key=lambda c: c["updated"], reverse=True)
        self.save()

    def new(self) -> dict:
        if not self.current["history"]:  # reuse an empty chat instead of piling them up
            return self.current
        chat = self._new()
        self.items.insert(0, chat)
        self.items = self.items[:KEEP_CHATS]
        self.current_id = chat["id"]
        self.save()
        return chat

    def switch(self, chat_id: str) -> None:
        if self.get(chat_id):
            self.current_id = chat_id
            self.save()

    def delete(self, chat_id: str) -> None:
        self.items = [c for c in self.items if c["id"] != chat_id]
        if not self.items:
            self.items = [self._new()]
        if self.get(self.current_id) is None:
            self.current_id = self.items[0]["id"]
        self.save()

    def save(self) -> None:
        config.set_pref("chats", self.items)
        config.set_pref("current_chat", self.current_id)
