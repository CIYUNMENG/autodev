"""LLM 客户端封装 - 支持 OpenAI、豆包 Doubao(火山引擎 Ark) 及兼容接口"""
import json
import logging
import time
from typing import Any

from openai import OpenAI

from app.config import settings

DEFAULT_LLM_TIMEOUT = 120

logger = logging.getLogger(__name__)


def _get_client_config() -> tuple[str, str, str] | None:
    """返回 (api_key, base_url, model)，未配置则返回 None"""
    provider = (settings.llm_provider or "openai").lower()
    if provider == "doubao":
        if settings.ark_api_key:
            return (
                settings.ark_api_key,
                settings.ark_base_url.rstrip("/"),
                settings.ark_model,
            )
        return None
    # openai 或默认
    if settings.openai_api_key:
        return (
            settings.openai_api_key,
            settings.openai_base_url.rstrip("/"),
            settings.openai_model,
        )
    return None


class LLMClient:
    """LLM 调用封装 - 支持 OpenAI / 豆包 Doubao"""

    def __init__(self):
        self._client: OpenAI | None = None
        self._model: str = "gpt-4o-mini"
        cfg = _get_client_config()
        if cfg:
            api_key, base_url, model = cfg
            self._client = OpenAI(api_key=api_key, base_url=base_url)
            self._model = model
            logger.info("LLM 已初始化: provider=%s, model=%s", settings.llm_provider, model)

    @property
    def is_available(self) -> bool:
        """检查 LLM 是否可用"""
        return self._client is not None

    def chat(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, str] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """
        调用 LLM 并返回文本内容
        :param messages: 消息列表
        :param response_format: 如 {"type": "json_object"} 用于强制 JSON 输出
        :param temperature: 温度参数
        """
        if not self.is_available:
            raise RuntimeError(
                "LLM 未配置: 请在 .env 中设置 OPENAI_API_KEY 或 ARK_API_KEY (LLM_PROVIDER=doubao)"
            )

        timeout = getattr(settings, "llm_timeout", DEFAULT_LLM_TIMEOUT)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "timeout": timeout,
        }
        # Doubao 对 response_format 支持可能异常，暂不使用
        use_format = response_format and (settings.llm_provider or "").lower() != "doubao"
        if use_format:
            kwargs["response_format"] = response_format
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            logger.info("LLM 调用开始 model=%s timeout=%ds messages=%d", self._model, timeout, len(messages))
            start = time.perf_counter()
            response = self._client.chat.completions.create(**kwargs)
            elapsed = time.perf_counter() - start
            content = response.choices[0].message.content
            # 部分 API 可能返回 content 为 dict（已解析）或列表
            if isinstance(content, dict):
                return json.dumps(content, ensure_ascii=False)
            if isinstance(content, list):
                text_parts = [
                    c.get("text", "") for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                content = "".join(text_parts) if text_parts else ""
            content = content or ""
            # 确保返回 str，处理 bytes
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            content_str = str(content)
            logger.info("LLM 调用完成 耗时 %.2fs 返回长度=%d", elapsed, len(content_str))
            return content_str
        except Exception as e:
            logger.exception("LLM 调用失败: %s", e)
            raise

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ):
        """
        流式调用 LLM，逐块 yield 文本。
        不传 response_format，以便流式输出。
        """
        if not self.is_available:
            raise RuntimeError(
                "LLM 未配置: 请在 .env 中设置 OPENAI_API_KEY 或 ARK_API_KEY (LLM_PROVIDER=doubao)"
            )
        timeout = getattr(settings, "llm_timeout", DEFAULT_LLM_TIMEOUT)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "timeout": timeout,
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        logger.info("LLM 流式调用开始 model=%s", self._model)
        try:
            stream = self._client.chat.completions.create(**kwargs)
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.exception("LLM 流式调用失败: %s", e)
            raise

    def chat_json(
        self, messages: list[dict[str, str]], temperature: float = 0.3
    ) -> dict[str, Any]:
        """调用 LLM 并解析为 JSON"""
        content = self.chat(
            messages,
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        return json.loads(content)

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """
        调用 LLM，支持 tool calling。
        返回 (content, tool_calls)。
        content 不为空时表示模型返回文本；tool_calls 不为空时表示模型请求调用工具。
        """
        if not self.is_available:
            raise RuntimeError(
                "LLM 未配置: 请在 .env 中设置 OPENAI_API_KEY 或 ARK_API_KEY (LLM_PROVIDER=doubao)"
            )
        timeout = getattr(settings, "llm_timeout", DEFAULT_LLM_TIMEOUT)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "timeout": timeout,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        logger.info("LLM tool calling 开始 model=%s tools=%d", self._model, len(tools))
        try:
            response = self._client.chat.completions.create(**kwargs)
            msg = response.choices[0].message
            content = msg.content or None
            if content and isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            content = str(content).strip() if content else None

            tool_calls: list[dict[str, Any]] = []
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if hasattr(tc, "function"):
                        fn = tc.function
                        name = getattr(fn, "name", "") or (fn.get("name") if isinstance(fn, dict) else "")
                        args_str = getattr(fn, "arguments", "") or (fn.get("arguments", "") if isinstance(fn, dict) else "")
                        try:
                            args = json.loads(args_str) if args_str else {}
                        except json.JSONDecodeError:
                            args = {}
                        tool_calls.append({
                            "id": getattr(tc, "id", ""),
                            "name": name,
                            "arguments": args,
                        })
            return content, tool_calls
        except Exception as e:
            logger.exception("LLM tool calling 失败: %s", e)
            raise
