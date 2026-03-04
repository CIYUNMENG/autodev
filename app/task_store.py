"""任务状态存储 - 用于异步生成时的进度查询，支持数量限制与 LRU 淘汰"""
from threading import Lock
from typing import Any

from app.config import settings
from app.schemas.state import TaskState

_store: dict[str, TaskState] = {}
_lock = Lock()


def _evict_if_needed() -> None:
    """超出上限时，按 updated_at 淘汰最旧任务"""
    max_size = getattr(settings, "task_store_max_size", 1000)
    if len(_store) < max_size:
        return
    # 按 updated_at 升序，淘汰最旧的
    ordered = sorted(
        _store.items(),
        key=lambda x: (x[1].updated_at or x[1].created_at).timestamp(),
    )
    to_remove = len(_store) - max_size + 1
    for i in range(to_remove):
        if i < len(ordered):
            del _store[ordered[i][0]]


def set_task(task_id: str, state: TaskState) -> None:
    with _lock:
        if task_id not in _store:
            _evict_if_needed()
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
