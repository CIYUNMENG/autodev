"""Agent 基类与接口定义 - 便于后续扩展记忆、规划等能力"""
from abc import ABC
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentCapabilities:
    """
    Agent 能力标志 - 用于声明 Agent 支持的能力，便于后续扩展。
    子类在定义时设置相应标志。
    """

    has_memory: bool = False      # 记忆（短期会话 / 长期持久）
    has_planning: bool = False    # 规划（任务分解、多步规划）
    has_tools: bool = False       # 工具调用
    has_reflection: bool = False  # 反思（self-critique、重试）
    has_rag: bool = False         # 检索增强（RAG）
    is_tool_agent: bool = False   # 工具型 Agent（无记忆、无规划，按输入产出）


class BaseAgent(ABC):
    """
    Agent 基类 - 定义通用接口与可选扩展点。
    子类按需实现 run() 或自定义入口方法；扩展能力通过 get_memory / plan / reflect 等 hook 实现。
    """

    capabilities: AgentCapabilities = AgentCapabilities()

    def get_memory(self) -> Any:
        """获取记忆（若支持）。默认返回 None。"""
        return None

    def set_memory(self, value: Any) -> None:
        """设置记忆（若支持）。默认无操作。"""
        pass

    def plan(self, *args: Any, **kwargs: Any) -> Any:
        """规划（若支持）。默认返回 None。"""
        return None

    def reflect(self, output: Any, *args: Any, **kwargs: Any) -> Any:
        """反思 / 自检（若支持）。默认直接返回 output。"""
        return output


class ToolAgentBase(BaseAgent):
    """
    工具型 Agent 基类 - 无记忆、无规划，每次调用输入完整，按输入产出输出。
    适用于 RequirementPlanningToolAgent、CodegenToolAgent 等。
    """

    capabilities = AgentCapabilities(is_tool_agent=True, has_tools=True)
