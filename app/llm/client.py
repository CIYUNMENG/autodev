"""LLM 客户端封装 - 基于 LiteLLM 统一接入 OpenAI、豆包及 100+ 模型"""
import json
import logging
import time
from typing import Any

import litellm

from app.config import settings

DEFAULT_LLM_TIMEOUT = 120

logger = logging.getLogger(__name__)


def _get_litellm_config() -> tuple[str, dict[str, Any]] | None:
    """
    根据 config 返回 (model, extra_kwargs)。
    extra_kwargs 含 api_key、api_base 等 LiteLLM 所需参数。
    未配置则返回 None。
    """
    # 若显式指定 LITELLM_MODEL，优先使用
    if getattr(settings, "litellm_model", "") and str(settings.litellm_model).strip():
        model = str(settings.litellm_model).strip()
        # 仍需要 api_key，按 provider 推断
        provider = (settings.llm_provider or "openai").lower()
        if provider == "doubao" and settings.ark_api_key:
            return model, {"api_key": settings.ark_api_key}
        if settings.openai_api_key:
            return model, {"api_key": settings.openai_api_key}
        return model, {}

    provider = (settings.llm_provider or "openai").lower()
    if provider == "doubao":
        if not settings.ark_api_key:
            return None
        model = f"volcengine/{settings.ark_model}"
        return model, {"api_key": settings.ark_api_key}
    # openai 或默认
    if not settings.openai_api_key:
        return None
    model = settings.openai_model
    extra: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url and "api.openai.com" not in settings.openai_base_url:
        extra["api_base"] = settings.openai_base_url.rstrip("/")
    return model, extra


class LLMClient:
    """LLM 调用封装 - 基于 LiteLLM，支持 OpenAI、豆包及 100+ 模型"""

    def __init__(self):
        self._model: str = "gpt-4o-mini"
        self._extra: dict[str, Any] = {}
        cfg = _get_litellm_config()
        if cfg:
            self._model, self._extra = cfg
            logger.info("LLM 已初始化 (LiteLLM): model=%s", self._model)

    @property
    def is_available(self) -> bool:
        """检查 LLM 是否可用"""
        return bool(self._model and (self._extra.get("api_key") or "openai" in self._model))

    def _base_kwargs(self) -> dict[str, Any]:
        timeout = getattr(settings, "llm_timeout", DEFAULT_LLM_TIMEOUT)
        return {
            "model": self._model,
            "timeout": timeout,
            **self._extra,
        }

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

        kwargs: dict[str, Any] = {
            **self._base_kwargs(),
            "messages": messages,
            "temperature": temperature,
        }
        if response_format and (settings.llm_provider or "").lower() != "doubao":
            kwargs["response_format"] = response_format
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            logger.info("LLM 调用开始 model=%s messages=%d", self._model, len(messages))
            start = time.perf_counter()
            response = litellm.completion(**kwargs)
            elapsed = time.perf_counter() - start
            content = response.choices[0].message.content
            if content is None:
                content = ""
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False)
            if isinstance(content, list):
                text_parts = [
                    c.get("text", "") for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                content = "".join(text_parts) if text_parts else ""
            content_str = str(content)
            if isinstance(content_str, bytes):
                content_str = content_str.decode("utf-8", errors="replace")
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
        """流式调用 LLM，逐块 yield 文本"""
        if not self.is_available:
            raise RuntimeError(
                "LLM 未配置: 请在 .env 中设置 OPENAI_API_KEY 或 ARK_API_KEY (LLM_PROVIDER=doubao)"
            )
        kwargs: dict[str, Any] = {
            **self._base_kwargs(),
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        logger.info("LLM 流式调用开始 model=%s", self._model)
        try:
            stream = litellm.completion(**kwargs)
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
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
        """
        if not self.is_available:
            raise RuntimeError(
                "LLM 未配置: 请在 .env 中设置 OPENAI_API_KEY 或 ARK_API_KEY (LLM_PROVIDER=doubao)"
            )
        kwargs: dict[str, Any] = {
            **self._base_kwargs(),
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        logger.info("LLM tool calling 开始 model=%s tools=%d", self._model, len(tools))
        try:
            response = litellm.completion(**kwargs)
            msg = response.choices[0].message
            content = msg.content or None
            if content and isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            content = str(content).strip() if content else None

            tool_calls: list[dict[str, Any]] = []
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_id = tc.id if hasattr(tc, "id") else (tc.get("id", "") if isinstance(tc, dict) else "")
                    fn = tc.function if hasattr(tc, "function") else (tc.get("function", {}) if isinstance(tc, dict) else {})
                    name = fn.name if hasattr(fn, "name") else (fn.get("name", "") if isinstance(fn, dict) else "")
                    args_str = fn.arguments if hasattr(fn, "arguments") else (fn.get("arguments", "") if isinstance(fn, dict) else "")
                    try:
                        args = json.loads(args_str) if args_str else {}
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append({"id": tc_id, "name": name, "arguments": args})
            return content, tool_calls
        except Exception as e:
            logger.exception("LLM tool calling 失败: %s", e)
            raise
