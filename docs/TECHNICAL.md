# AutoDev Agent 技术说明文档

## 1. 项目概述

AutoDev Agent 是以 **AI 实时对话** 为核心的自主软件工程系统：用户通过自然语言描述项目 → 系统进行需求分析 → 自动完成代码生成。代码生成及后续扩展能力均以**工具**形式封装，可被对话、HTTP API、MCP 统一调用。

### 1.1 核心特性

- **对话优先**：网页聊天支持流式/非流式交互，可多轮补充需求后一键生成
- **AI 自主决策**：使用 LLM tool calling，AI 根据用户意图自行判断是否调用工具，无需关键词规则
- **工具层抽象**：生成项目、查询进度等均为注册工具，供 `/api/tools/*`、MCP、对话统一调用
- **可扩展**：新工具注册后自动对对话可见，无需修改业务逻辑

### 1.2 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.10+（兼容 3.13） |
| Web 框架 | FastAPI |
| 数据校验 | Pydantic v2 |
| LLM 调用 | LiteLLM（统一接入 OpenAI、豆包、100+ 模型）+ LangChain（编排、记忆、RAG） |
| 可选 | MCP (Model Context Protocol)，供 Cursor/Claude 等调用 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           调用入口层                                      │
│  /chat (Web) │ /api/chat/* │ /api/tools/* │ /api/generate* │ MCP (/mcp)   │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           工具层 (agent_tools)                            │
│  registry: register / run / to_openai_tools                               │
│  工具: generate_project │ get_progress                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
┌─────────────────┐       ┌─────────────────────┐       ┌─────────────────┐
│  chat_routes    │       │  generate_project   │       │  get_progress   │
│  LLM + 工具循环  │       │  → Orchestrator     │       │  → task_store   │
└─────────────────┘       └─────────────────────┘       └─────────────────┘
          │                           │
          │                           ▼
          │               ┌─────────────────────┐
          │               │   Orchestrator      │
          │               │ 需求规划 → 代码生成   │
          │               └─────────────────────┘
          │                           │
          │                           ▼
          │               ┌─────────────────────────────┐
          │               │ RequirementPlanningToolAgent │  (需求+规划)
          │               │ CodegenToolAgent             │  (代码生成，非 MCP)
          │               └─────────────────────────────┘
          │                           │
          └───────────────────────────┴───────────────────────────► LLMClient
```

### 2.2 目录结构

```
app/
├── main.py              # FastAPI 入口，MCP 挂载
├── config.py            # 配置（Pydantic Settings）
├── orchestrator.py      # 编排：需求分析 → 规划 → 代码生成
├── core/
│   └── tools.py         # 工具抽象：Tool、ToolResult
├── agent_tools/         # 业务工具
│   ├── __init__.py      # 工具注册
│   ├── registry.py      # 注册、执行、to_openai_tools
│   ├── generate_project.py
│   └── get_progress.py
├── api/
│   ├── routes.py        # 兼容 API：/api/generate、/api/progress
│   ├── chat_routes.py   # 聊天 API，LLM + 工具循环
│   └── tool_routes.py   # 工具 HTTP API：/api/tools/*
├── mcp_server.py        # MCP 服务（可选）
├── agents/              # 工具型 Agent + 接口定义
│   ├── base.py          # BaseAgent、AgentCapabilities、ToolAgentBase
│   ├── protocols.py     # IHaveMemory、ICanPlan、ICanReflect、IToolAgent
│   ├── main_agent.py    # RequirementPlanningToolAgent：需求分析 + 规划
│   └── tool_agent.py    # CodegenToolAgent：按规划生成代码（非 MCP）
├── llm/
│   └── client.py        # LLM 客户端（基于 LiteLLM）
├── integrations/
│   └── langchain_llm.py # LangChain ChatLiteLLM，供 chains、memory 等
├── schemas/             # Pydantic 模型
│   ├── state.py         # TaskState、TaskPhase
│   ├── requirement.py
│   └── planning.py
├── chat_store.py        # 聊天会话存储
├── task_store.py        # 任务状态存储
└── tools/               # 文件系统等基础设施
```

---

## 3. 核心模块说明

### 3.1  Orchestrator（编排器）

**职责**：串联主 Agent（需求+规划）与工具 Agent（代码生成）。

**流程**：
1. **RequirementPlanningToolAgent**：`analyze_and_plan(topic)` 或 `plan_only(requirement)` → 生成 `RequirementOutput` 与 `PlanningOutput`
2. **CodegenToolAgent**：`generate_from_plan()` 按 FilePlan 单文件生成（支持多线程并发）

若规划结果为空（`file_plans` 为空），任务标记为 FAILED 并返回，不执行代码生成。

**RequirementPlanningToolAgent 与 CodegenToolAgent 的关系**：前者负责理解意图、产出结构化需求与规划；后者负责按规划生成代码，均为 Orchestrator 内部调用的工具型 Agent，**不是** MCP 工具。MCP 工具是 `generate_project`、`get_progress`，由 mcp_server 暴露给 Cursor/Claude 等外部客户端。

### 3.2 RequirementPlanningToolAgent / CodegenToolAgent / MCP 的区别

| 概念 | 说明 |
|------|------|
| **RequirementPlanningToolAgent** | 需求规划工具 Agent，负责需求分析 + 规划。由 Orchestrator 调用，不对外暴露。 |
| **CodegenToolAgent** | 代码生成工具 Agent，负责按 FilePlan 生成代码。由 Orchestrator 调用，**不是** MCP 工具。 |
| **MCP 工具** | `generate_project`、`get_progress`，由 `mcp_server.py` 暴露，供 Cursor/Claude 等客户端通过 MCP 协议调用。 |

**工具型 Agent 不属于 MCP**。MCP 是「模型调用工具」的协议（LLM → MCP Server → 工具），本项目的 MCP 工具是 `generate_project` 和 `get_progress`；CodegenToolAgent 是 Orchestrator 在 `generate_project` 内部调用的代码生成组件。

### 3.3 Agent 接口定义

| 文件 | 内容 | 用途 |
|------|------|------|
| `base.py` | `BaseAgent`、`AgentCapabilities`、`ToolAgentBase` | 基类与能力标志，便于后续扩展 |
| `protocols.py` | `IHaveMemory`、`ICanPlan`、`ICanReflect`、`IToolAgent` | typing 协议，结构性子类型 |

**AgentCapabilities** 声明 Agent 支持的能力：`has_memory`、`has_planning`、`has_tools`、`has_reflection`、`has_rag`、`is_tool_agent`。当前工具型 Agent 仅设置 `is_tool_agent=True`，其余为默认 `False`。

**BaseAgent** 提供可选扩展点：`get_memory()`、`set_memory()`、`plan()`、`reflect()`，默认均为 no-op，子类按需实现。

**ToolAgentBase** 继承 BaseAgent，声明 `is_tool_agent=True`，适用于 RequirementPlanningToolAgent、CodegenToolAgent 等无记忆、无规划的工具型 Agent。后续为 Chat Agent 增加记忆、规划时，可继承 BaseAgent 并实现相应 hook。

### 3.4 工具层（agent_tools）

**抽象**（`app/core/tools.py`）：
- `Tool`：抽象基类，子类实现 `run(**kwargs) -> ToolResult`
- `ToolResult`：`ok`、`data`、`error`

**注册表**（`app/agent_tools/registry.py`）：
- `register(tool)`：注册工具
- `run(name, **kwargs)`：按名称执行
- `to_openai_tools()`：转为 OpenAI tool calling 格式

**现有工具**：
- `generate_project`：启动项目生成，支持同步/异步，返回 task_id
- `get_progress`：根据 task_id 查询进度（TaskState）

### 3.5 聊天与 LLM 工具循环

**流程**（`chat_routes._run_tool_call_loop`）：
1. 构建系统提示（含工具说明、generate_project 前需确认细节等）
2. 循环：调用 `LLMClient.chat_with_tools(messages, tools)` → 解析 content / tool_calls
3. 若有 tool_calls：执行工具 → 将结果 append 到 messages → 继续下一轮
4. 若无 tool_calls：返回 content 给用户
5. 最多 10 轮，超时返回「处理超时，请重试。」

**系统提示要点**：
- 需求模糊时先追问，不要直接调用 generate_project
- generate_project 成功后直接回复用户 task_id，不在此轮内调用 get_progress

### 3.6 LLM 客户端

**支持**：
- OpenAI：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`
- 豆包/火山引擎 Ark：`LLM_PROVIDER=doubao`、`ARK_API_KEY`、`ARK_BASE_URL`、`ARK_MODEL`

**方法**：
- `chat()`：普通文本对话
- `chat_json()`：JSON 输出
- `chat_stream()`：流式输出
- `chat_with_tools()`：tool calling，返回 `(content, tool_calls)`

---

## 4. 数据流与状态

### 4.1 任务状态（TaskState）

| 字段 | 说明 |
|------|------|
| project_id | 项目 ID（proj_xxx） |
| topic | 用户输入的主题 |
| phase | 当前阶段（INIT / REQUIREMENT_ANALYSIS / PLANNING / CODE_GENERATION / COMPLETED / FAILED） |
| requirement | 需求分析结果 |
| planning | 规划结果 |
| progress | 进度（total_files、completed_files、failed_files） |
| completed_steps | 已完成步骤列表 |
| output_path | 生成项目路径 |
| created_at / updated_at | 时间戳 |

### 4.2 存储

- **chat_store**：内存存储，`ChatSession`（session_id、messages、topic_full、requirement、task_id）
- **task_store**：内存存储，`task_id -> TaskState`，供 get_progress 查询
- **文件**：`generated_projects/` 下按 project_id 创建目录，`_stages/` 保存各阶段输入输出

---

## 5. API 设计

### 5.1 聊天

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /chat | 聊天页面 |
| POST | /api/chat/message | 非流式消息 |
| POST | /api/chat/message/stream | SSE 流式消息 |
| POST | /api/chat/generate | 基于当前会话开始生成 |

### 5.2 工具

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/tools | 列出工具 |
| POST | /api/tools/generate_project | 生成项目 |
| POST | /api/tools/get_progress | 查询进度 |

### 5.3 兼容 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/generate | 同步生成 |
| POST | /api/generate/async | 异步生成，返回 task_id |
| GET | /api/progress/{task_id} | 查询进度 |

### 5.4 MCP

- 端点：`/mcp`（需安装 `mcp[cli]`）
- 工具：`generate_project`、`get_progress`
- 可通过环境变量 `AUTODEV_ENABLE_MCP=0` 关闭挂载

---

## 6. 配置说明

### 6.1 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| LLM_PROVIDER | openai / doubao | openai |
| OPENAI_API_KEY | OpenAI API Key | - |
| OPENAI_BASE_URL | OpenAI 基础 URL | https://api.openai.com/v1 |
| OPENAI_MODEL | 模型 | gpt-4o-mini |
| ARK_API_KEY | 火山引擎 Ark Key | - |
| ARK_BASE_URL | Ark 基础 URL | https://ark.cn-beijing.volces.com/api/v3 |
| ARK_MODEL | Ark 模型 | doubao-seed-1-6-251015 |
| llm_timeout | LLM 超时秒数 | 120 |
| log_level | 日志级别 | INFO |
| AUTODEV_ENABLE_MCP | 是否启用 MCP | 1 |

### 6.2 配置文件

- `.env`：环境变量，优先于默认值
- `app/config.py`：Pydantic Settings，`env_file=".env"`

---

## 7. 日志与排查

- **控制台**：使用 UTF8StreamHandler，避免 Windows 下中文乱码
- **文件**：`logs/autodev.log`，便于排查卡住/超时
- **关键日志**：`[proj_xxx]` 为项目 ID，`[requirement]`、`[planning]`、`[codegen]` 为阶段

---

## 8. 扩展指南

### 8.1 新增工具

1. 在 `app/agent_tools/` 下实现继承 `Tool` 的类
2. 在 `app/agent_tools/__init__.py` 中 `register()` 注册
3. 按需在 `tool_routes.py`、`mcp_server.py` 中暴露 HTTP/MCP 端点

详见 [TOOLS.md](./TOOLS.md)。

### 8.2 新增 Agent

1. 在 `app/agents/` 下实现分析/规划/代码生成逻辑
2. 在 `orchestrator.py` 中接入对应阶段

---

## 版本

- 文档版本：随代码同步
- 项目版本：v0.1.0 MVP
