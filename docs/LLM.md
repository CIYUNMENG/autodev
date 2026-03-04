# LLM 与 LangChain 集成说明

## 技术栈

| 组件 | 作用 |
|------|------|
| **LiteLLM** | 统一 LLM 接入层，支持 100+ 模型（OpenAI、Anthropic、豆包、本地模型等） |
| **LangChain** | 编排、记忆、RAG 等扩展能力，后续可接入 chains、agents、memory |

## 配置

与之前一致，通过 `.env` 配置：

- **OpenAI**：`LLM_PROVIDER=openai`，`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`
- **豆包 / 火山引擎 Ark**：`LLM_PROVIDER=doubao`，`ARK_API_KEY`、`ARK_MODEL`

新增可选：

- **LITELLM_MODEL**：直接指定 LiteLLM 模型字符串，如 `openai/gpt-4o`、`volcengine/doubao-seed-1-6-251015`，覆盖上述推断

## 使用方式

### 1. 现有调用（不变）

`LLMClient` 已基于 LiteLLM 实现，接口保持不变：

```python
from app.llm import LLMClient

client = LLMClient()
client.chat([{"role": "user", "content": "你好"}])
client.chat_json(messages, temperature=0.3)
client.chat_with_tools(messages, tools)
```

### 2. LangChain ChatModel（供 chains、memory 等）

```python
from app.integrations import get_chat_model

llm = get_chat_model(temperature=0.3)
# 用于 LCEL chain
# chain = llm | output_parser
# 或 ConversationChain + memory
```

## 目录结构

```
app/
├── llm/
│   └── client.py          # LLMClient，基于 LiteLLM
├── integrations/
│   ├── __init__.py
│   └── langchain_llm.py   # get_chat_model()，返回 LangChain ChatLiteLLM
```
