"""确认需求工具：当 AI 判断需求已完整时调用，运行 RequirementPlanningToolAgent 并保存到 session"""
from typing import Any

from app.chat_store import get_session, update_session
from app.core.tools import Tool, ToolResult
from app.llm import LLMClient


class ConfirmRequirementTool(Tool):
    """
    确认需求工具：AI 在对话中判断需求已完整时调用。
    运行 RequirementPlanningToolAgent 分析+规划，保存 requirement 到 ChatSession，
    返回需求摘要供前端渲染「需求卡片」。
    生成由用户在卡片上点击「生成」触发，不由 AI 调用 generate_project。
    """

    name = "confirm_requirement"
    description = "当用户已完整描述项目需求（类型、语言、功能等）后调用，将需求结构化并保存，供用户确认后点击生成。不要在需求模糊时调用。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "聊天会话 ID"},
            "topic": {"type": "string", "description": "用户描述的项目主题（对话中积累的完整需求）"},
        },
        "required": ["session_id", "topic"],
    }

    def run(
        self,
        *,
        session_id: str,
        topic: str,
        **kwargs: Any,
    ) -> ToolResult:
        session_id = (session_id or "").strip()
        topic = (topic or "").strip()
        if not session_id:
            return ToolResult(ok=False, error="session_id 不能为空")
        if not topic:
            return ToolResult(ok=False, error="topic 不能为空")

        session = get_session(session_id)
        if not session:
            return ToolResult(ok=False, error="会话不存在或已过期")

        try:
            from app.agents import RequirementPlanningToolAgent

            agent = RequirementPlanningToolAgent(LLMClient())
            requirement, planning = agent.analyze_and_plan(topic, stages_dir=None)
            if not requirement.is_sufficient:
                return ToolResult(
                    ok=False,
                    error="需求仍不充分",
                    data={"missing_info": requirement.missing_info},
                )
            req_dict = requirement.model_dump()
            update_session(
                session_id,
                requirement=req_dict,
                is_sufficient=True,
            )
            return ToolResult(
                ok=True,
                data={
                    "session_id": session_id,
                    "requirement": req_dict,
                    "message": "需求已确认，用户可在卡片上点击生成",
                },
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            return ToolResult(ok=False, error=str(e))
