"""反思模块 - 生产者-批评者模型，失败时分析原因并返回修正建议"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

REFLECT_ON_ERROR_SYSTEM = """你是一名资深软件工程师，负责代码审阅与问题诊断。你的任务是：当代码生成失败时，分析失败原因并给出具体、可执行的修正建议。

你的输出将直接用于指导下一次代码生成，因此请：
1. 明确指出的问题类型：语法错误、导入缺失、类型不匹配、接口契约违反、框架 API 误用等
2. 给出 1～3 条简洁的修正建议，每条建议应具体到「改什么、怎么改」
3. 若错误信息涉及行号，指出可能的原因
4. 用中文输出，语言简明扼要，不要冗长解释
5. 直接输出修正建议，不要输出 markdown 标题或代码块"""

REFLECT_ON_ERROR_USER = """代码生成任务失败，请分析原因并给出修正建议。

**目标文件**: {file_path}

**失败信息**:
{error}

**额外上下文**（如有）:
{context}

请输出 1～3 条具体修正建议，供下一次生成参考。"""


def reflect_on_error(
    llm: Any,
    error: str,
    file_path: str,
    context: dict[str, Any] | None = None,
) -> str:
    """
    批评者：根据生成失败时的错误，分析原因并返回修正建议。
    供 CodegenToolAgent 等失败后重试时使用。

    :param llm: LLMClient 实例
    :param error: 异常信息或失败原因
    :param file_path: 生成目标文件路径
    :param context: 可选上下文，如 prompt 摘要、依赖等
    :return: 修正建议文本，将追加到重试的 prompt 中
    """
    ctx_str = str(context or "")
    user_content = REFLECT_ON_ERROR_USER.format(
        error=error,
        file_path=file_path,
        context=ctx_str[:2000],
    )
    try:
        suggestion = llm.chat(
            messages=[
                {"role": "system", "content": REFLECT_ON_ERROR_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        return (suggestion or "").strip()
    except Exception as e:
        logger.warning("反思调用失败，跳过修正建议: %s", e)
        return ""
