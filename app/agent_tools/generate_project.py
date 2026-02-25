"""生成项目工具：封装 Orchestrator，供对话/API/MCP 调用"""

import threading
import uuid
from typing import Any

from app.core.tools import Tool, ToolResult
from app.orchestrator import Orchestrator
from app.schemas.state import TaskPhase, TaskState
from app.task_store import get_task, set_task


def _run_and_store(task_id: str, topic: str, requirement: dict | None = None) -> None:
    try:
        def on_update(s: TaskState) -> None:
            set_task(task_id, s)

        state = Orchestrator().run(
            topic, on_state_update=on_update, requirement=requirement
        )
        set_task(task_id, state)
    except Exception:
        import traceback
        traceback.print_exc()


class GenerateProjectTool(Tool):
    """根据主题（及可选已确认需求）异步生成项目，返回 task_id"""

    name = "generate_project"
    description = "根据项目主题或已确认需求，在后台生成完整项目（需求分析→规划→代码生成），返回 task_id，可通过 get_progress 轮询进度。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "项目主题描述"},
            "session_id": {"type": "string", "description": "可选，聊天会话 ID"},
            "requirement": {
                "type": "object",
                "description": "可选，已确认的需求（从聊天传入时使用）",
            },
        },
        "required": ["topic"],
    }

    def run(
        self,
        *,
        topic: str,
        session_id: str | None = None,
        requirement: dict | None = None,
        async_mode: bool = True,
        **kwargs: Any,
    ) -> ToolResult:
        topic = (topic or "").strip()
        if not topic:
            return ToolResult(ok=False, error="topic 不能为空")

        task_id = f"task_{uuid.uuid4().hex[:12]}"
        initial = TaskState(
            project_id=task_id,
            topic=topic,
            phase=TaskPhase.REQUIREMENT_ANALYSIS,
        )
        set_task(task_id, initial)

        if async_mode:
            t = threading.Thread(
                target=_run_and_store,
                args=(task_id, topic, requirement),
                daemon=True,
            )
            t.start()
            return ToolResult(
                ok=True,
                data={
                    "task_id": task_id,
                    "session_id": session_id,
                    "message": "生成已启动，请通过 get_progress 轮询进度",
                },
            )
        else:
            _run_and_store(task_id, topic, requirement)
            state = get_task(task_id)
            return ToolResult(
                ok=True,
                data={"task_id": task_id, "state": state.model_dump(mode="json") if state else None},
            )
