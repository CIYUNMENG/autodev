"""任务状态存储 - 用于异步生成时的进度查询"""
from threading import Lock
from typing import Any

from app.schemas.state import TaskState

_store: dict[str, TaskState] = {}
_lock = Lock()


def set_task(task_id: str, state: TaskState) -> None:
    with _lock:
        _store[task_id] = state


def get_task(task_id: str) -> TaskState | None:
    with _lock:
        return _store.get(task_id)


def update_task(task_id: str, **kwargs: Any) -> None:
    with _lock:
        if task_id in _store:
            s = _store[task_id]
            for k, v in kwargs.items():
                if hasattr(s, k):
                    setattr(s, k, v)
