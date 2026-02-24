"""API 路由"""
import json
import threading
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.orchestrator import Orchestrator
from app.schemas.state import TaskState
from app.task_store import get_task, set_task

router = APIRouter(prefix="/api", tags=["projects"])


class GenerateRequest(BaseModel):
    """生成请求"""

    topic: str = Field(..., min_length=1, description="项目主题，如：一个待办事项 API 服务")


async def _parse_body_utf8(request: Request) -> GenerateRequest:
    """显式按 UTF-8 解析请求体，失败时尝试 GBK（兼容部分 Windows 客户端）"""
    body = await request.body()
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("gbk", errors="replace")
    data = json.loads(text)
    topic = (data.get("topic") or "").strip()
    if not topic:
        from fastapi import HTTPException
        raise HTTPException(400, "topic 不能为空")
    return GenerateRequest(topic=topic)


def _run_and_store(task_id: str, topic: str) -> None:
    try:
        def on_update(s: TaskState) -> None:
            set_task(task_id, s)

        state = Orchestrator().run(topic, on_state_update=on_update)
        set_task(task_id, state)
    except Exception:
        import traceback
        traceback.print_exc()


@router.post("/generate", response_model=TaskState)
async def generate_project(req: GenerateRequest = Depends(_parse_body_utf8)):
    """同步生成：阻塞直到完成，返回完整状态（含 progress）"""
    orchestrator = Orchestrator()
    state = orchestrator.run(req.topic.strip())
    return state


@router.post("/generate/async")
async def generate_project_async(req: GenerateRequest = Depends(_parse_body_utf8)):
    """异步生成：立即返回 task_id，后台线程执行，可通过 GET /api/progress/{task_id} 轮询进度"""
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    state = TaskState(project_id=task_id, topic=req.topic)
    set_task(task_id, state)
    # 使用独立线程，避免 BackgroundTasks 占用 worker 导致轮询请求被阻塞
    t = threading.Thread(target=_run_and_store, args=(task_id, req.topic.strip()), daemon=True)
    t.start()
    return {"task_id": task_id, "message": "任务已提交，请轮询 GET /api/progress/{task_id}"}


@router.get("/progress/{task_id}", response_model=TaskState | None)
def get_progress(task_id: str):
    """查询任务进度（用于异步生成）"""
    return get_task(task_id)


@router.get("/health")
def health():
    """健康检查"""
    return {"status": "ok", "service": "AutoDev Agent"}
