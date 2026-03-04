"""工具 API：统一暴露工具层，供前端/外部调用"""

import asyncio
import json

from fastapi import APIRouter, Request

from app.agent_tools import list_tools, run as tool_run

router = APIRouter(prefix="/api/tools", tags=["tools"])


async def _parse_json_utf8(request: Request) -> dict:
    body = await request.body()
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("gbk", errors="replace")
    return json.loads(text) if text.strip() else {}


@router.get("")
async def tools_list():
    """列出所有已注册工具（名称、描述、参数 schema）"""
    return {"tools": await asyncio.to_thread(list_tools)}


@router.post("/generate_project")
async def api_generate_project(request: Request):
    """
    调用 generate_project 工具。
    Body: { "topic": "项目主题", "session_id": "可选", "requirement": {}, "async_mode": true }
    """
    data = await _parse_json_utf8(request)
    topic = (data.get("topic") or "").strip()
    session_id = (data.get("session_id") or "").strip() or None
    requirement = data.get("requirement")
    async_mode = data.get("async_mode", True)

    result = await asyncio.to_thread(
        tool_run,
        "generate_project",
        topic=topic,
        session_id=session_id,
        requirement=requirement,
        async_mode=async_mode,
    )
    if not result.ok:
        return {"ok": False, "error": result.error}
    return {"ok": True, "data": result.data}


@router.post("/get_progress")
async def api_get_progress(request: Request):
    """
    调用 get_progress 工具。
    Body: { "task_id": "task_xxx" }
    """
    data = await _parse_json_utf8(request)
    task_id = (data.get("task_id") or "").strip()
    result = await asyncio.to_thread(tool_run, "get_progress", task_id=task_id)
    if not result.ok:
        return {"ok": False, "error": result.error}
    return {"ok": True, "data": result.data}
