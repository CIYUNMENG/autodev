"""工具抽象：供对话/API/MCP 统一调用的接口"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """工具执行结果，统一返回格式"""

    ok: bool = Field(..., description="是否成功")
    data: Any = Field(default=None, description="成功时返回的数据")
    error: str | None = Field(default=None, description="失败时的错误信息")


class Tool(ABC):
    """可被对话/API/MCP 调用的工具基类"""

    name: str = ""
    description: str = ""
    parameters_schema: dict[str, Any] | None = None

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        """执行工具，返回统一结果"""
        ...
