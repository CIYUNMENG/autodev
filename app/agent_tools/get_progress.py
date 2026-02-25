"""查询任务进度工具：供 API/MCP 调用"""

from app.core.tools import Tool, ToolResult
from app.task_store import get_task


class GetProgressTool(Tool):
    """根据 task_id 查询生成任务进度"""

    name = "get_progress"
    description = "根据 task_id 查询项目生成任务的当前进度与状态。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务 ID，由 generate_project 返回"},
        },
        "required": ["task_id"],
    }

    def run(self, *, task_id: str, **kwargs) -> ToolResult:
        task_id = (task_id or "").strip()
        if not task_id:
            return ToolResult(ok=False, error="task_id 不能为空")
        state = get_task(task_id)
        if not state:
            return ToolResult(ok=False, error="任务不存在或已完成")
        return ToolResult(ok=True, data=state.model_dump(mode="json"))
