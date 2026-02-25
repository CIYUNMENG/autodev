"""业务工具：可被对话/API/MCP 调用的能力"""

from app.agent_tools.confirm_requirement import ConfirmRequirementTool
from app.agent_tools.generate_project import GenerateProjectTool
from app.agent_tools.get_progress import GetProgressTool
from app.agent_tools.registry import get, list_tools, register, run, to_openai_tools

# 注册内置工具
register(ConfirmRequirementTool())
register(GenerateProjectTool())
register(GetProgressTool())

# 聊天专用工具（不含 generate_project，生成由用户点击卡片触发）
CHAT_TOOL_NAMES = ["confirm_requirement", "get_progress"]

__all__ = [
    "CHAT_TOOL_NAMES",
    "ConfirmRequirementTool",
    "GenerateProjectTool",
    "GetProgressTool",
    "get",
    "list_tools",
    "register",
    "run",
    "to_openai_tools",
]
