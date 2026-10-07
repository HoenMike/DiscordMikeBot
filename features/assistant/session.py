from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


SessionKey = Tuple[int, int, int]


@dataclass
class ConversationTurn:
    user: str
    assistant: str


@dataclass
class ConversationSession:
    key: SessionKey
    last_response_message_id: int
    updated_at: float
    intent: str = "chat"
    turns: List[ConversationTurn] = field(default_factory=list)


class SessionStore:
    """Small in-memory continuation store for Asumi 3.1.

    This is intentionally not a transcript database. Sessions expire quickly and
    keep only a bounded number of compact user/assistant turns.
    """

    def __init__(self, ttl_seconds: float = 20 * 60, max_turns: int = 4):
        self.ttl_seconds = max(60.0, float(ttl_seconds))
        self.max_turns = max(1, int(max_turns))
        self._sessions: Dict[SessionKey, ConversationSession] = {}

    @staticmethod
    def key_for(message) -> Optional[SessionKey]:
        guild = getattr(message, "guild", None)
        channel = getattr(message, "channel", None)
        author = getattr(message, "author", None)
        guild_id = getattr(guild, "id", None)
        channel_id = getattr(channel, "id", None)
        author_id = getattr(author, "id", None)
        if guild_id is None or channel_id is None or author_id is None:
            return None
        return int(guild_id), int(channel_id), int(author_id)

    def _is_expired(self, session: ConversationSession, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        return (now - session.updated_at) > self.ttl_seconds

    def get(self, message) -> Optional[ConversationSession]:
        key = self.key_for(message)
        if key is None:
            return None
        session = self._sessions.get(key)
        if session is None:
            return None
        if self._is_expired(session):
            self._sessions.pop(key, None)
            return None
        return session

    def is_live_reply(self, message) -> bool:
        session = self.get(message)
        if session is None:
            return False
        reference = getattr(message, "reference", None)
        reply_id = getattr(reference, "message_id", None)
        return bool(reply_id and int(reply_id) == session.last_response_message_id)

    def record_exchange(
        self,
        message,
        response_message_id: int,
        user_text: str,
        assistant_text: str,
        intent: str = "chat",
    ) -> Optional[ConversationSession]:
        key = self.key_for(message)
        if key is None:
            return None

        now = time.monotonic()
        current = self._sessions.get(key)
        turns = [] if current is None or self._is_expired(current, now) else list(current.turns)
        turns.append(ConversationTurn(user=user_text.strip(), assistant=assistant_text.strip()))
        turns = turns[-self.max_turns :]

        session = ConversationSession(
            key=key,
            last_response_message_id=int(response_message_id),
            updated_at=now,
            intent=intent,
            turns=turns,
        )
        self._sessions[key] = session
        return session

    def clear(self, message) -> None:
        key = self.key_for(message)
        if key is not None:
            self._sessions.pop(key, None)
