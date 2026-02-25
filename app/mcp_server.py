"""
MCP (Model Context Protocol) 服务：暴露工具供 Cursor / Claude 等客户端调用。
需安装 mcp：pip install mcp[cli]
挂载到 FastAPI 后，MCP 端点位于 /mcp，与主应用共享进程与 task_store。
"""

from __future__ import annotations

from typing import Any


def create_mcp_app():
    """创建 FastMCP 的 ASGI 应用，供 main 挂载。未安装 mcp 时返回 None。"""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        return None

    from app.agent_tools import run as tool_run

    mcp = FastMCP("AutoDev Agent", json_response=True)

    @mcp.tool()
    def generate_project(
        topic: str,
        session_id: str | None = None,
        requirement: dict[str, Any] | None = None,
        async_mode: bool = True,
    ) -> dict[str, Any]:
        """根据项目主题（及可选已确认需求）生成完整项目。async_mode 为 True 时立即返回 task_id，可通过 get_progress 轮询进度。"""
        result = tool_run(
            "generate_project",
            topic=topic,
            session_id=session_id,
            requirement=requirement,
            async_mode=async_mode,
        )
        if not result.ok:
            return {"ok": False, "error": result.error}
        return {"ok": True, "data": result.data}

    @mcp.tool()
    def get_progress(task_id: str) -> dict[str, Any]:
        """根据 task_id 查询项目生成任务的当前进度与状态。"""
        result = tool_run("get_progress", task_id=task_id)
        if not result.ok:
            return {"ok": False, "error": result.error}
        return {"ok": True, "data": result.data}

    # 挂载到 FastAPI 的 /mcp 路径；兼容不同 MCP SDK 版本的 ASGI 入口
    for attr in ("streamable_http_app", "get_asgi_app", "http_app", "sse_app"):
        if hasattr(mcp, attr):
            return getattr(mcp, attr)()
    raise RuntimeError("MCP SDK 未提供 ASGI 应用入口")
