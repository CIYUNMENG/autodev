"""Agent 协议定义 - 用于 typing / 结构性子类型，便于后续扩展"""
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IHaveMemory(Protocol):
    """支持记忆的 Agent 协议"""

    def get_memory(self) -> Any: ...
    def set_memory(self, value: Any) -> None: ...


@runtime_checkable
class ICanPlan(Protocol):
    """支持规划的 Agent 协议"""

    def plan(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class ICanReflect(Protocol):
    """支持反思的 Agent 协议"""

    def reflect(self, output: Any, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class IToolAgent(Protocol):
    """工具型 Agent 协议 - 无记忆、无规划，按输入产出"""

    def run(self, **kwargs: Any) -> Any: ...
