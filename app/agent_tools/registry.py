"""工具注册表：按 name 查找并执行"""

import logging
from typing import Any

from app.core.tools import Tool, ToolResult

logger = logging.getLogger(__name__)

_registry: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    """注册一个工具"""
    if not tool.name:
        raise ValueError("Tool must have a name")
    _registry[tool.name] = tool
    logger.debug("注册工具: %s", tool.name)


def get(name: str) -> Tool | None:
    """按名称获取工具"""
    return _registry.get(name)


def list_tools() -> list[dict[str, Any]]:
    """返回所有已注册工具的名称与描述（供 MCP/API 展示）"""
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters_schema": t.parameters_schema,
        }
        for t in _registry.values()
    ]


def to_openai_tools(tool_names: list[str] | None = None) -> list[dict[str, Any]]:
    """转为 OpenAI / 兼容 API 的 tools 格式，供 LLM tool calling 使用。
    tool_names 为 None 时返回全部；否则只返回指定名称的工具。"""
    if tool_names is not None:
        tools = [t for t in _registry.values() if t.name in tool_names]
    else:
        tools = list(_registry.values())
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters_schema or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


def run(name: str, **kwargs: Any) -> ToolResult:
    """执行指定名称的工具"""
    tool = _registry.get(name)
    if not tool:
        return ToolResult(ok=False, error=f"未知工具: {name}")
    try:
        return tool.run(**kwargs)
    except Exception as e:
        logger.exception("工具执行失败 %s: %s", name, e)
        return ToolResult(ok=False, error=str(e))
