# AutoDev Agent

以 **AI 实时对话** 为核心的自主软件工程系统：聊天式描述项目 → 需求分析 → 代码生成；代码生成与后续能力均以**工具**形式提供，可被对话、HTTP API、MCP 统一调用。

## 功能

- **对话优先**：网页聊天（`/chat`）支持流式/非流式需求分析，可多轮补充需求后一键生成
- **工具层**：生成项目、查询进度等为注册工具，供 `/api/tools/*` 与 MCP 调用
- **需求分析**：检查信息充分性，生成结构化需求（含 missing_info、assumptions）
- **规划与代码生成**：按 FilePlan 单文件生成，支持多线程并发
- **可选 MCP**：安装 `mcp[cli]` 后，MCP 端点挂载于 `/mcp`，供 Cursor/Claude 等调用

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，按需选择：

**OpenAI**
```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
```

**豆包 Doubao / 火山引擎 Ark**
```
LLM_PROVIDER=doubao
ARK_API_KEY=你的 Ark API Key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=doubao-seed-1-6-251015
```

### 3. 启动服务

```bash
python run.py
```

> Windows 下 `run.py` 会自动以 UTF-8 模式重启，解决日志/HTTP/控制台中文乱码。若直接使用 uvicorn，请加 `-X utf8`：  
> `python -X utf8 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

### 4. 调用 API

**同步生成**（阻塞直到完成）

```bash
# CMD
curl -X POST "http://localhost:8000/api/generate" -H "Content-Type: application/json; charset=utf-8" -d "{\"topic\": \"一个待办事项 API 服务\"}"

# PowerShell（中文不乱码需先设置控制台编码）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Invoke-RestMethod -Method POST -Uri "http://localhost:8000/api/generate" -ContentType "application/json; charset=utf-8" -Body '{"topic": "一个待办事项 API 服务"}'
```

**异步生成**（立即返回 task_id，轮询进度）

```bash
# 提交
curl -X POST "http://localhost:8000/api/generate/async" -H "Content-Type: application/json" -d '{"topic": "一个待办事项 API 服务"}'
# 返回 {"task_id": "task_xxx", ...}

# 轮询进度
curl "http://localhost:8000/api/progress/task_xxx"
```

**网页聊天**：访问 http://localhost:8000/chat —— 聊天式描述项目，可实时补充需求，无编码问题

**工具 API**：`GET /api/tools` 列出工具；`POST /api/tools/generate_project`、`POST /api/tools/get_progress` 调用对应工具

**MCP**：安装 `mcp[cli]` 后启动服务，MCP 端点为 `http://localhost:8000/mcp`，可供 Cursor/Claude 等配置后调用

**Swagger 文档**：访问 http://localhost:8000/docs

## 项目结构

```
AutoDevAgent/
├── app/
│   ├── main.py          # FastAPI 入口（含可选 MCP 挂载）
│   ├── config.py        # 配置
│   ├── orchestrator.py  # Agent 编排（需求→规划→代码生成）
│   ├── core/            # 核心抽象：Tool、ToolResult
│   ├── agent_tools/     # 业务工具：generate_project、get_progress、注册表
│   ├── mcp_server.py    # MCP 服务（挂载到 /mcp）
│   ├── api/             # API 路由（chat、tools、projects 兼容）
│   ├── agents/          # RequirementPlanningToolAgent + CodegenToolAgent
│   ├── llm/             # LLM 客户端
│   ├── schemas/         # Pydantic 模型
│   └── tools/           # 文件系统等基础设施
├── docs/
│   └── TOOLS.md         # 工具层说明与新增工具步骤
├── .cursor/skills/      # Cursor Skill：autodev-tools
├── generated_projects/  # 生成的项目输出目录
├── requirements.txt
└── README.md
```

## 技术栈

- Python 3.10+
- FastAPI
- Pydantic
- OpenAI API（或兼容接口）

## 版本

v0.1.0 - MVP
