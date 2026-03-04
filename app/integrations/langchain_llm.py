"""LangChain + LiteLLM 集成：提供 ChatModel，供 chains、agents、memory 等使用"""
import logging
from typing import Any

from app.llm.client import _get_litellm_config

logger = logging.getLogger(__name__)


def get_chat_model(
    temperature: float = 0.7,
    **kwargs: Any,
) -> Any:
    """
    返回配置好的 LangChain ChatModel（基于 ChatLiteLLM）。
    供后续构建 chains、agents、带 memory 的对话等使用。

    使用示例：
        from app.integrations import get_chat_model
        llm = get_chat_model(temperature=0.3)
        # 用于 LCEL chain
        chain = llm | output_parser
        # 或用于 ConversationChain + memory
    """
    try:
        from langchain_litellm import ChatLiteLLM
    except ImportError:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            try:
                from langchain_community.chat_models import ChatLiteLLM
            except ImportError:
                logger.warning("langchain-litellm 或 langchain-community 未安装，无法使用 get_chat_model")
                return None

    cfg = _get_litellm_config()
    if not cfg:
        logger.warning("LLM 未配置，get_chat_model 返回 None")
        return None

    model, extra = cfg
    # ChatLiteLLM 直接接受 model、temperature、api_key、api_base 等
    params: dict[str, Any] = {"model": model, "temperature": temperature}
    if extra.get("api_key"):
        params["api_key"] = extra["api_key"]
    if extra.get("api_base"):
        params["api_base"] = extra["api_base"]

    return ChatLiteLLM(**params, **kwargs)
