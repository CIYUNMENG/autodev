# AutoDev Agent 工具层说明

本文档说明如何在本项目中**新增或修改可被对话/API/MCP 调用的工具**，保证架构一致与兼容性。

## 架构概览

- **对话优先**：主入口为 AI 实时对话（`/chat`、`/api/chat/message`、`/api/chat/message/stream`）。
- **工具层**：代码生成、后续功能（重构、测试、部署等）均以**工具**形式注册，由对话/API/MCP 统一调用。
- **AI 自主决策**：对话使用 LLM tool calling，AI 根据用户意图自行判断是否调用工具，无需关键词规则；**新工具注册后自动对对话可见**。
- **统一执行**：`app.agent_tools.registry` 提供 `register(tool)`、`run(name, **kwargs)`、`list_tools()`、`to_openai_tools()`，所有调用方通过同一入口执行。

## 如何新增一个工具

### 1. 实现工具类

在 `app/agent_tools/` 下新建模块（如 `refactor.py`），实现继承自 `app.core.tools.Tool` 的类：

- 必须实现 `run(self, **kwargs) -> ToolResult`。
- 类属性：`name`（唯一）、`description`（供 MCP/API 展示）、可选 `parameters_schema`（JSON Schema）。

示例：

```python
from app.core.tools import Tool, ToolResult

class RefactorTool(Tool):
    name = "refactor"
    description = "对指定文件或目录进行重构，支持重命名、提取函数等。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件或目录路径"},
            "action": {"type": "string", "enum": ["rename", "extract"]},
        },
        "required": ["path", "action"],
    }

    def run(self, *, path: str, action: str, **kwargs) -> ToolResult:
        # 实现逻辑，返回 ToolResult(ok=True, data=...) 或 ToolResult(ok=False, error="...")
        ...
```

### 2. 注册工具

在 `app/agent_tools/__init__.py` 中：

- `from app.agent_tools.refactor import RefactorTool`
- `register(RefactorTool())`

### 3. 暴露给 API（可选）

若需 HTTP 调用，在 `app/api/tool_routes.py` 中增加对应端点，例如：

- `@router.post("/refactor")`，解析 body 后调用 `tool_run("refactor", **data)`，返回 `{"ok": ..., "data": ...}`。

### 4. 暴露给 MCP（可选）

在 `app/mcp_server.py` 的 `create_mcp_app()` 内增加 `@mcp.tool()` 包装函数，内部调用 `tool_run("refactor", ...)`，与现有 `generate_project`、`get_progress` 一致。

## 约束与兼容

- **不破坏现有 API**：`/api/generate`、`/api/generate/async`、`/api/progress/{task_id}`、`/api/chat/*` 保持行为不变，内部改为调用工具层。
- **工具幂等与错误**：`run()` 返回 `ToolResult`，调用方根据 `ok` 与 `error` 处理；工具内部应对异常做捕获并返回 `ToolResult(ok=False, error=...)`。
- **MCP 可选**：未安装 `mcp[cli]` 时主服务照常运行，仅不挂载 `/mcp`。

## 目录与职责

| 路径 | 职责 |
|------|------|
| `app/core/tools.py` | 工具抽象 `Tool`、`ToolResult` |
| `app/agent_tools/registry.py` | 注册、按 name 执行、列出工具 |
| `app/agent_tools/generate_project.py` | 生成项目工具（封装 Orchestrator） |
| `app/agent_tools/get_progress.py` | 查询任务进度工具 |
| `app/api/tool_routes.py` | 工具 HTTP API（`/api/tools/*`） |
| `app/mcp_server.py` | MCP 服务（挂载到 `/mcp`） |

新增工具时只需：实现 `Tool` 子类 → 在 `__init__.py` 中 `register` → 按需在 `tool_routes` 与 `mcp_server` 中暴露。
