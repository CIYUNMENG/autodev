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


def list_tasks() -> list[dict[str, Any]]:
    """列出所有任务，按 updated_at 降序，供仪表盘使用"""
    with _lock:
        items = list(_store.items())
    result = []
    for task_id, state in items:
        result.append({
            "task_id": task_id,
            "project_id": state.project_id,
            "topic": state.topic,
            "phase": state.phase.value,
            "output_path": state.output_path,
            "progress": state.progress.model_dump() if state.progress else {},
            "created_at": state.created_at.isoformat() if state.created_at else None,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        })
    result.sort(key=lambda x: (x["updated_at"] or ""), reverse=True)
    return result
