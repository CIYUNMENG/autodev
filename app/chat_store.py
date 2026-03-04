"""聊天会话存储 - 用于网页聊天式需求收集，支持 JSON 持久化与数量限制、LRU 淘汰"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_SESSIONS_FILE = _DATA_DIR / "chat_sessions.json"


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _session_to_dict(s: "ChatSession") -> dict:
    return {
        "session_id": s.session_id,
        "messages": [{"role": m.role, "content": m.content} for m in s.messages],
        "topic_full": s.topic_full,
        "requirement": s.requirement,
        "is_sufficient": s.is_sufficient,
        "task_id": s.task_id,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _dict_to_session(d: dict) -> "ChatSession":
    msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in d.get("messages", [])]
    upd = d.get("updated_at")
    if isinstance(upd, str):
        try:
            upd = datetime.fromisoformat(upd.replace("Z", "+00:00"))
        except Exception:
            upd = None
    return ChatSession(
        session_id=d["session_id"],
        messages=msgs,
        topic_full=d.get("topic_full", ""),
        requirement=d.get("requirement"),
        is_sufficient=d.get("is_sufficient", False),
        task_id=d.get("task_id"),
        updated_at=upd,
    )


def _save() -> None:
    _ensure_data_dir()
    with _lock:
        data = {sid: _session_to_dict(s) for sid, s in _store.items()}
    with open(_SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load() -> None:
    if not _SESSIONS_FILE.exists():
        return
    try:
        with open(_SESSIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        with _lock:
            for sid, d in data.items():
                try:
                    _store[sid] = _dict_to_session(d)
                except Exception:
                    pass
    except Exception:
        pass


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
    updated_at: datetime | None = None


_store: dict[str, ChatSession] = {}
_lock = Lock()

# 启动时加载持久化数据
_load()


def _evict_if_needed() -> None:
    """超出上限时，按 updated_at 淘汰最旧会话"""
    from app.config import settings
    max_sessions = getattr(settings, "chat_store_max_sessions", 200)
    if len(_store) < max_sessions:
        return
    ordered = sorted(
        _store.items(),
        key=lambda x: (x[1].updated_at or datetime(1970, 1, 1)).timestamp(),
    )
    to_remove = len(_store) - max_sessions + 1
    for i in range(to_remove):
        if i < len(ordered):
            del _store[ordered[i][0]]


def persist_session(session_id: str) -> None:
    """将会话变更持久化到磁盘（在 append messages 后调用）"""
    with _lock:
        if session_id in _store:
            _store[session_id].updated_at = datetime.now()
    _save()


def create_session() -> ChatSession:
    import uuid

    sid = f"chat_{uuid.uuid4().hex[:12]}"
    s = ChatSession(session_id=sid, updated_at=datetime.now())
    with _lock:
        _evict_if_needed()
        _store[sid] = s
    _save()
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
            s.updated_at = datetime.now()
    _save()


def append_message(session_id: str, role: str, content: str) -> None:
    """追加消息并持久化"""
    with _lock:
        if session_id in _store:
            s = _store[session_id]
            s.messages.append(ChatMessage(role=role, content=content))
            s.updated_at = datetime.now()
    _save()


def list_sessions() -> list[dict[str, Any]]:
    """列出所有会话，按 updated_at 降序，供侧边栏展示"""
    with _lock:
        items = list(_store.items())
    result = []
    for sid, s in items:
        title = "新对话"
        for m in s.messages:
            if m.role == "user" and m.content.strip():
                title = m.content.strip()
                if len(title) > 40:
                    title = title[:37] + "..."
                break
        if title == "新对话" and s.topic_full.strip():
            t = s.topic_full.strip()
            title = t[:37] + "..." if len(t) > 40 else t
        result.append({
            "session_id": sid,
            "title": title,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })
    result.sort(key=lambda x: (x["updated_at"] or ""), reverse=True)
    return result
