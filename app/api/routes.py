"""API 路由（兼容保留；内部通过工具层执行）"""
import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.agent_tools import run as tool_run

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


@router.post("/generate")
async def generate_project(req: GenerateRequest = Depends(_parse_body_utf8)):
    """同步生成：阻塞直到完成，返回完整状态（含 progress）"""
    result = tool_run(
        "generate_project",
        topic=req.topic.strip(),
        async_mode=False,
    )
    if not result.ok:
        from fastapi import HTTPException
        raise HTTPException(500, result.error or "生成失败")
    state = result.data.get("state")
    if not state:
        from fastapi import HTTPException
        raise HTTPException(500, "未返回状态")
    return state


@router.post("/generate/async")
async def generate_project_async(req: GenerateRequest = Depends(_parse_body_utf8)):
    """异步生成：立即返回 task_id，后台线程执行，可通过 GET /api/progress/{task_id} 轮询进度"""
    result = tool_run(
        "generate_project",
        topic=req.topic.strip(),
        async_mode=True,
    )
    if not result.ok:
        from fastapi import HTTPException
        raise HTTPException(500, result.error or "提交失败")
    task_id = result.data.get("task_id")
    return {"task_id": task_id, "message": "任务已提交，请轮询 GET /api/progress/{task_id}"}


@router.get("/progress/{task_id}")
def get_progress(task_id: str):
    """查询任务进度（用于异步生成），通过工具层"""
    result = tool_run("get_progress", task_id=task_id)
    if not result.ok:
        return None
    return result.data


@router.get("/tasks")
def list_tasks_api():
    """列出所有任务，供仪表盘使用"""
    from app.task_store import list_tasks
    return {"tasks": list_tasks()}


@router.get("/health")
def health():
    """健康检查"""
    return {"status": "ok", "service": "AutoDev Agent"}
