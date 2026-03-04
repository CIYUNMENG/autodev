# MultiUserClaw MVP 学习版指南

面向从头学习、逐步扩展的 MVP 版本。以 Web 为主入口，不依赖 CLI，不包含各渠道 SDK（Telegram、Discord 等）。  
目标：在此 MVP 基础上逐步添加功能，最终达到并超越完整版。

---

## 一、MVP 范围与扩展路径

### 1.1 MVP 包含

| 模块 | 技术 | 说明 |
|------|------|------|
| 入口 | `nanobot web` | Web 为主，CLI 可选 |
| Web | FastAPI + Uvicorn | HTTP + WebSocket |
| Agent | AgentLoop + ContextBuilder | ReAct 循环、上下文组装 |
| LLM | LiteLLM | 统一多模型调用 |
| 消息 | MessageBus (asyncio.Queue) | 渠道与 Agent 解耦 |
| 会话 | SessionManager | JSONL 持久化 |
| 工具 | read_file、write_file、list_dir、exec、web_search、web_fetch | 最小工具集 |
| 配置 | Pydantic + JSON | 配置加载 |

### 1.2 不包含（后续可加）

- Platform 网关、Docker、PostgreSQL、多租户
- 各渠道 SDK（Telegram、Discord、飞书等）
- Cron、Heartbeat、Plugins、子 Agent

### 1.3 扩展路线建议

```
MVP (当前)
  ├─ 加 Cron → 定时任务
  ├─ 加 Memory 巩固 → 记忆系统
  ├─ 加 Skills → 技能系统
  ├─ 加 Plugin → 插件
  ├─ 加 BaseChannel 新渠道 → Telegram/Discord...
  └─ 加 Platform → 多租户、Docker、PostgreSQL
```

---

## 二、快速启动（Web 优先）

```bash
# 1. 安装
pip install -e .

# 2. 配置：创建 ~/.nanobot/config.json（或运行 nanobot onboard 生成）
# 至少配置 model 和 providers.xxx.apiKey

# 3. 启动 Web
nanobot web
# 浏览器访问 http://localhost:18080（需有前端或 WebSocket 客户端）
```

如需完整前端，使用 `python start_local.py` 启动 nanobot + platform + frontend。

---

## 三、各技术实现思路与关键函数

### 3.1 MessageBus（消息总线）

| 项目 | 说明 |
|------|------|
| **实现思路** | 使用 `asyncio.Queue` 解耦生产者（渠道）与消费者（Agent），避免渠道与 Agent 强耦合 |
| **文件** | `nanobot/bus/queue.py`、`nanobot/bus/events.py` |
| **关键函数** | `publish_inbound()`、`consume_inbound()`、`publish_outbound()`、`consume_outbound()` |
| **扩展性** | 新渠道只需实现 BaseChannel，向 bus 发布 InboundMessage；Agent 无需改动 |

```python
# bus/queue.py
class MessageBus:
    inbound: asyncio.Queue[InboundMessage]
    outbound: asyncio.Queue[OutboundMessage]
```

---

### 3.2 AgentLoop（ReAct 主循环）

| 项目 | 说明 |
|------|------|
| **实现思路** | 从 bus 消费消息 → 组装上下文 → 循环：调用 LLM → 若有 tool_calls 则执行工具并追加结果 → 直至无 tool_calls 得到最终回复 |
| **文件** | `nanobot/agent/loop.py` |
| **关键函数** | `run()` 长驻消费；`process_direct()` 单次同步；`_process_message()` 单条处理；`_run_agent_loop()` 迭代循环 |
| **稳定性** | `max_iterations` 限制循环；工具异常返回错误字符串，不抛异常；会话持久化保证可恢复 |

```python
# 核心循环 _run_agent_loop()
while iteration < self.max_iterations:
    response = await self.provider.chat(messages, tools, model)
    if response.has_tool_calls:
        for tc in response.tool_calls:
            result = await self.tools.execute(tc.name, tc.arguments)
            messages = self.context.add_tool_result(...)
    else:
        final_content = response.content
        break
```

---

### 3.3 ContextBuilder（上下文组装）

| 项目 | 说明 |
|------|------|
| **实现思路** | 将 identity、bootstrap 文件、记忆、Skills 摘要、历史消息组装成完整的 system + messages，供 LLM 使用 |
| **文件** | `nanobot/agent/context.py` |
| **关键函数** | `build_system_prompt()`、`build_messages()`、`add_assistant_message()`、`add_tool_result()` |
| **扩展性** | 新 bootstrap 文件、新 memory 来源、新 skills 只需在 `build_system_prompt()` 中追加；保持单一职责 |

```python
# 典型结构
system = identity + bootstrap + memory + skills_summary
messages = [{"role":"system","content":system}] + history + [{"role":"user","content":current}]
```

---

### 3.4 LiteLLMProvider（LLM 调用）

| 项目 | 说明 |
|------|------|
| **实现思路** | 通过 Provider 注册表按模型名路由到对应 API，统一调用 `litellm.acompletion()`，解析返回的 content/tool_calls |
| **文件** | `nanobot/providers/litellm_provider.py`、`nanobot/providers/registry.py` |
| **关键函数** | `chat()` 主调用；`_resolve_model()` 解析模型前缀；`_setup_env()` 设置 API Key 环境变量；`find_by_model()` 查注册表 |
| **扩展性** | 新 Provider 在 registry 中加 `ProviderSpec` 即可，无需改 `litellm_provider.py` |

```python
# 核心调用
response = await acompletion(
    model=litellm_model,
    messages=messages,
    tools=tool_definitions,
)
# 解析 content、tool_calls、usage
```

---

### 3.5 ToolRegistry（工具注册与执行）

| 项目 | 说明 |
|------|------|
| **实现思路** | 维护 `name -> Tool` 映射；`get_definitions()` 生成 OpenAI function 定义；`execute()` 先校验参数再调用 `tool.execute()` |
| **文件** | `nanobot/agent/tools/registry.py`、`nanobot/agent/tools/base.py` |
| **关键函数** | `register()`、`get_definitions()`、`execute()`；`Tool.validate_params()`、`Tool.execute()` |
| **扩展性** | 新工具继承 `Tool`，实现 `name`、`description`、`parameters`、`execute()`，然后 `registry.register()` |

```python
# base.py
class Tool(ABC):
    @abstractmethod
    async def execute(self, **kwargs) -> str: ...
    def to_schema(self) -> dict: ...  # OpenAI function 格式
```

---

### 3.6 SessionManager（会话持久化）

| 项目 | 说明 |
|------|------|
| **实现思路** | 会话按 `channel:chat_id` 为 key，存为 JSONL 文件；`get_or_create()` 懒加载；`save()` 全量写入 |
| **文件** | `nanobot/session/manager.py` |
| **关键函数** | `get_or_create(key)`、`save(session)`、`get_history()`、`list_sessions()` |
| **稳定性** | JSONL 可读可追查；Session 对象包含 `messages`、`last_consolidated` 等，支持后续记忆巩固 |

```python
# 存储路径
# {workspace}/sessions/{safe_key}.jsonl
```

---

### 3.7 WebChannel（Web 渠道）

| 项目 | 说明 |
|------|------|
| **实现思路** | 继承 `BaseChannel`；`start()` 时创建 FastAPI app 并用 uvicorn 启动；WebSocket 收消息后 `_handle_message()` 发布到 bus；从 bus 消费 outbound 后 `send()` 推送到 WebSocket |
| **文件** | `nanobot/channels/web.py`、`nanobot/channels/base.py`、`nanobot/web/server.py` |
| **关键函数** | `WebChannel.start()`、`stop()`、`send()`；`create_app()` 创建 FastAPI；WebSocket `/ws/{session_id}` 处理收发 |
| **扩展性** | 新渠道实现 `BaseChannel` 的 `start`、`stop`、`send`，在 ChannelManager 中按配置初始化即可 |

```python
# BaseChannel 接口
class BaseChannel(ABC):
    async def start(self): ...
    async def stop(self): ...
    async def send(self, msg: OutboundMessage): ...
```

---

### 3.8 配置系统

| 项目 | 说明 |
|------|------|
| **实现思路** | `~/.nanobot/config.json` 存 JSON；`load_config()` 读取并 `Config.model_validate()`；Pydantic 负责校验与默认值 |
| **文件** | `nanobot/config/loader.py`、`nanobot/config/schema.py` |
| **关键函数** | `load_config()`、`get_config_path()`、`Config.model_validate()` |

---

## 四、关键目录与阅读顺序

```
nanobot/
├── bus/queue.py, events.py    # 1. 消息结构
├── agent/loop.py              # 2. Agent 主循环
├── agent/context.py           # 3. 上下文组装
├── providers/litellm_provider.py  # 4. LLM 调用
├── agent/tools/registry.py, base.py  # 5. 工具
├── session/manager.py         # 6. 会话
├── channels/base.py, web.py   # 7. 渠道抽象与 Web
├── web/server.py              # 8. FastAPI 路由
└── config/                    # 9. 配置
```

---

## 五、MVP 稳定性与扩展性设计

| 方面 | 设计 |
|------|------|
| **解耦** | MessageBus 隔离渠道与 Agent；Provider 注册表隔离模型；Tool 抽象隔离能力 |
| **错误处理** | 工具异常返回字符串，不中断循环；`max_iterations` 防止死循环 |
| **持久化** | 会话 JSONL 可恢复；工作区文件作为记忆与技能载体 |
| **扩展点** | 新渠道 = 实现 BaseChannel；新工具 = 实现 Tool 并 register；新 Provider = 加 ProviderSpec；新 Skills = 在 context 中挂载 |

---

## 六、从 MVP 到完整版的路线图

1. **MVP 稳固**：理解上述各模块，能单用户 Web 对话
2. **+ Cron**：在 `cron/service.py` 中加定时调度，调用 `process_direct`
3. **+ Memory 巩固**：在 AgentLoop 中加记忆归纳逻辑
4. **+ Skills**：在 ContextBuilder 中加 skills 加载
5. **+ 新渠道**：实现 `BaseChannel`，在 ChannelManager 中注册
6. **+ Platform**：引入 Gateway、PostgreSQL、Docker，实现多租户

---

## 七、常见问题

| 问题 | 处理 |
|------|------|
| No API key configured | 配置 `~/.nanobot/config.json` 中 `providers.xxx.apiKey` 或 `.env` 中 `*_API_KEY` |
| 模型名格式 | `provider/model`，如 `dashscope/qwen3-coder-plus` |
| 会话目录 | `~/.nanobot/sessions/*.jsonl` |
| 工作区 | `~/.nanobot/workspace` |
