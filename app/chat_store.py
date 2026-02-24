"""聊天会话存储 - 用于网页聊天式需求收集"""
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class ChatSession:
    session_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    topic_full: str = ""
    requirement: dict[str, Any] | None = None
    is_sufficient: bool = False
    task_id: str | None = None


_store: dict[str, ChatSession] = {}
_lock = Lock()


def create_session() -> ChatSession:
    import uuid
    sid = f"chat_{uuid.uuid4().hex[:12]}"
    s = ChatSession(session_id=sid)
    with _lock:
        _store[sid] = s
    return s


def get_session(session_id: str) -> ChatSession | None:
    with _lock:
        return _store.get(session_id)


def update_session(session_id: str, **kwargs: Any) -> None:
    with _lock:
        if session_id in _store:
            s = _store[session_id]
            for k, v in kwargs.items():
                if hasattr(s, k):
                    setattr(s, k, v)
