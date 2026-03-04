# 更新记录

## 2025-03-03

- **反思（Reflection）**：CodegenToolAgent 失败时调用批评者 `reflect_on_error` 获取修正建议并重试 1 次；prompt 位于 `app/agents/reflection.py` 与 `tool_agent.py`
- **LiteLLM**：LLM 层改为 LiteLLM，统一接入 OpenAI、豆包及 100+ 模型，支持 `LITELLM_MODEL` 覆盖
- **LangChain**：新增 `app/integrations/langchain_llm.py`，提供 `get_chat_model()` 供后续 chains、memory、RAG 等使用
- **异步非阻塞**：所有 API 路由中的同步阻塞调用改为 `asyncio.to_thread`，避免阻塞事件循环
- **task_store 淘汰**：增加 `task_store_max_size`（默认 1000），超出时按 LRU 淘汰最旧任务
- **chat_store 淘汰**：增加 `chat_store_max_sessions`（默认 200），超出时按 LRU 淘汰最旧会话
- **配置**：`TASK_STORE_MAX_SIZE`、`CHAT_STORE_MAX_SESSIONS` 可经 `.env` 覆盖

## 2025-02-23

- **创建项目**：实现代码生成功能，创建聊天功能

## 2025-02-24

- **聊天侧边栏**：左侧固定侧边栏，新建聊天、历史会话切换，JSON 持久化
- **仪表盘**：任务列表、状态展示、定时刷新
- **任务管理**：task_store、GET /api/tasks，生成任务卡片确认任务
- **Agent**：confirm_requirement 工具，需求确认与生成分离，需求卡片展示
- **白天/黑夜主题**：主题切换、localStorage 持久化、径向扩散过渡动画
- **布局修复**：header 遮挡、侧边栏固定、内容区滚动
