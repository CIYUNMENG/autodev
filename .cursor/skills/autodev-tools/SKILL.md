---
name: autodev-tools
description: 在 AutoDev Agent 中新增或修改可被对话/API/MCP 调用的工具时使用。用于保持工具层架构一致与兼容性。
---

# AutoDev Agent 工具层

## 何时使用本 Skill

- 需要新增一个可被对话、HTTP API 或 MCP 调用的「工具」（如代码生成、重构、测试、部署等）。
- 需要修改现有工具（generate_project、get_progress）的行为或参数。
- 需要理解对话/API/MCP 如何统一调用工具。

## 核心约定

1. **工具统一入口**：所有工具在 `app/agent_tools/` 中实现，通过 `app.agent_tools.registry` 的 `register(tool)` 注册，通过 `run(name, **kwargs)` 执行。
2. **AI 自主决策**：对话使用 LLM tool calling，`to_openai_tools()` 将已注册工具转为 OpenAI 格式；**新工具注册后自动对对话可见**，AI 自行判断是否调用。
3. **接口**：每个工具是 `app.core.tools.Tool` 的子类，实现 `run(**kwargs) -> ToolResult`；提供 `name`、`description`、`parameters_schema`（供 LLM 理解）。
4. **不破坏现有 API**：`/api/generate`、`/api/chat/*`、`/api/progress/{task_id}` 等行为保持不变，内部只改为调用工具层。

## 新增工具步骤

1. 在 `app/agent_tools/` 新建模块，定义继承 `Tool` 的类，实现 `run()` 并返回 `ToolResult`。
2. 在 `app/agent_tools/__init__.py` 中 `register(YourTool())`。
3. 若需 HTTP：在 `app/api/tool_routes.py` 增加 `POST /api/tools/xxx`，内部调用 `tool_run("xxx", **body)`。
4. 若需 MCP：在 `app/mcp_server.py` 的 `create_mcp_app()` 中增加 `@mcp.tool()` 包装，内部调用 `tool_run("xxx", ...)`。

## 详细说明

参见项目根目录下 `docs/TOOLS.md`。
