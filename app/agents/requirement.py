"""需求分析 Agent"""
import logging
from pathlib import Path
from typing import Any

from app.llm import LLMClient
from app.schemas.requirement import RequirementOutput
from app.stages import save_requirement_stage

logger = logging.getLogger(__name__)

REQUIREMENT_PROMPT = """你是一个专业的需求分析师。根据用户描述的项目主题，分析并输出结构化的需求文档。

## 用户输入的项目主题
{topic}

## 要求
1. **必须识别用户明确指定的编程语言**：如 C++/cpp、Python/python、JavaScript、Java 等，未指定时默认为 python
2. **判断信息充分性**：若主题过于模糊（如仅「做个东西」），设置 is_sufficient=false 并列出 missing_info
3. 若信息不足但可推断，基于合理假设补充，填入 assumptions
4. 输出必须为合法 JSON，且严格符合以下 schema

## 输出 JSON Schema
{{
  "project_type": "web_app / api_service / cli_tool / lib / native_app 等",
  "programming_language": "python / cpp / javascript / java / go 等，用户明确要求时必须准确提取",
  "target_users": "目标用户描述",
  "core_features": ["功能1", "功能2", ...],
  "non_functional_requirements": ["性能", "可维护性", "安全", ...],
  "is_sufficient": true或false,
  "missing_info": ["缺失项1", ...] 或 [],
  "assumptions": ["假设1", ...] 或 []
}}

请直接输出 JSON，不要包含其他文字。"""


def _normalize_raw_requirement(raw: dict[str, Any]) -> dict[str, Any]:
    """将 LLM 原始 JSON 规范化为 RequirementOutput 所需字段"""
    lang = (raw.get("programming_language") or "python").strip().lower()
    lang_map = {"c++": "cpp", "c": "c", "js": "javascript", "ts": "typescript"}
    lang = lang_map.get(lang, lang)
    proj_type = (raw.get("project_type") or "web_app").strip() or "cli_tool"
    return {
        "project_type": proj_type,
        "programming_language": lang,
        "target_users": raw.get("target_users", ""),
        "core_features": raw.get("core_features") or [],
        "non_functional_requirements": raw.get("non_functional_requirements") or [],
        "is_sufficient": raw.get("is_sufficient", True),
        "missing_info": raw.get("missing_info") or [],
        "assumptions": raw.get("assumptions") or [],
    }


class RequirementAgent:
    """需求分析 Agent"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    @classmethod
    def parse_raw(cls, raw: dict[str, Any]) -> RequirementOutput:
        """从 LLM 原始 JSON 解析为 RequirementOutput"""
        return RequirementOutput.model_validate(_normalize_raw_requirement(raw))

    def analyze(self, topic: str, stages_dir: Path | None = None) -> RequirementOutput:
        """分析项目主题，返回结构化需求。stages_dir 不为空时保存输入输出到该目录"""
        logger.info("需求分析开始: topic=%s", topic[:50])
        prompt = REQUIREMENT_PROMPT.format(topic=topic)

        raw = self.llm.chat_json(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        result = self.parse_raw(raw)
        if stages_dir:
            save_requirement_stage(stages_dir, prompt, result.model_dump())
        logger.info(
            "需求分析完成: project_type=%s, language=%s",
            result.project_type,
            result.programming_language,
        )
        return result
