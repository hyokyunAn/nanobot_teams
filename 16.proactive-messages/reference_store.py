"""Persistent store for ConversationReference by chat_id."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from botbuilder.schema import ConversationReference


class ConversationReferenceStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()
        self._refs: dict[str, ConversationReference] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for chat_id, item in raw.items():
            self._refs[chat_id] = ConversationReference.deserialize(item)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = {chat_id: ref.serialize() for chat_id, ref in self._refs.items()}
        self.path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def upsert(self, chat_id: str, reference: ConversationReference) -> None:
        async with self._lock:
            self._refs[chat_id] = reference
            self._save()

    async def get(self, chat_id: str) -> ConversationReference | None:
        async with self._lock:
            return self._refs.get(chat_id)

