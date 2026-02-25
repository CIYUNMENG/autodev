"""主 Agent - 合并需求分析与规划，负责理解用户意图并输出结构化需求与文件级规划"""
import logging
from pathlib import Path
from typing import Any

from app.agents.base import ToolAgentBase
from app.llm import LLMClient
from app.schemas.planning import FilePlan, PlanningOutput
from app.schemas.requirement import RequirementOutput
from app.stages import save_requirement_stage, save_planning_stage

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

PLANNING_PROMPT = """你是一个软件架构师。根据需求文档，输出项目文件级规划。

## 需求文档
{requirement_json}

## 要求
1. 将项目拆分为具体的源文件，每个文件列出：职责、类、接口、函数、设计模式、依赖
2. 必须包含 requirements.txt（Python）或 package.json（JS）或等价依赖文件、README.md
3. 依赖的 path 必须是 file_plans 中其他文件的 path
4. suggested_order 按依赖拓扑排序，无依赖的文件在前
5. **跨文件接口契约（通用）**：不区分 Model/View/Controller，凡被依赖方调用、连接或「连入」的接口，均需在对应文件的 classes 中写明。
   - **对外提供**：若文件 A 依赖文件 B，且 A 会调用 B 中类的方法或连接 B 中类的信号，则 B 的 classes 中必须明确列出这些方法/信号及完整签名。
   - **对外接收**：若文件 A 会将某信号（来自 A 或其它模块）连接到 B 中某类的槽/方法，则 B 的 classes 中必须明确列出该槽/方法的签名（例如 update_history_list(history)、show_error(msg)）。
   classes 中应写成「类名: 职责说明。必须定义信号/方法: xxx(type)、yyy()；必须实现槽/方法: zzz(arg)」等形式。
6. **技术栈**：在 frameworks_used 中列出本项目将使用的主要框架/库（如 PyQt5、tkinter、Django、FastAPI），便于代码生成阶段应用预置 API 约束。

## 输出 JSON Schema
{{
  "architecture": "整体架构描述，如 MVC、分层架构等",
  "file_plans": [
    {{
      "path": "相对路径如 app/main.py",
      "purpose": "文件职责",
      "classes": ["ClassName: 说明。对外提供的方法/信号及对外接收的槽/方法均需写出完整签名"],
      "interfaces": ["接口名"],
      "functions": ["函数签名 说明"],
      "design_pattern": "设计模式",
      "dependencies": ["依赖的文件path"]
    }}
  ],
  "suggested_order": ["path1", "path2", ...],
  "frameworks_used": ["PyQt5", "Django", ...]
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


class RequirementPlanningToolAgent(ToolAgentBase):
    """需求规划工具 Agent：需求分析 + 规划，负责理解用户意图并产出结构化需求与文件级规划"""

    def __init__(self, llm: LLMClient):
        super().__init__()
        self.llm = llm

    def analyze_and_plan(
        self, topic: str, stages_dir: Path | None = None
    ) -> tuple[RequirementOutput, PlanningOutput]:
        """
        根据用户主题，依次完成需求分析与规划。
        返回 (RequirementOutput, PlanningOutput)。
        若 requirement.is_sufficient 为 False，planning 可能未执行（调用方需先检查）。
        """
        logger.info("主 Agent 开始: topic=%s", topic[:50])

        # Step 1: 需求分析
        prompt_req = REQUIREMENT_PROMPT.format(topic=topic)
        raw_req = self.llm.chat_json(
            messages=[{"role": "user", "content": prompt_req}],
            temperature=0.3,
        )
        requirement = RequirementOutput.model_validate(_normalize_raw_requirement(raw_req))
        if stages_dir:
            save_requirement_stage(stages_dir, prompt_req, requirement.model_dump())
        logger.info("需求分析完成: project_type=%s, language=%s", requirement.project_type, requirement.programming_language)

        if not requirement.is_sufficient:
            logger.info("信息不足，跳过规划")
            return requirement, PlanningOutput(architecture="", file_plans=[], suggested_order=[], frameworks_used=[])

        # Step 2: 规划
        req_json = requirement.model_dump_json(exclude_none=True)
        prompt_plan = PLANNING_PROMPT.format(requirement_json=req_json)
        raw_plan = self.llm.chat_json(
            messages=[{"role": "user", "content": prompt_plan}],
            temperature=0.2,
        )
        arch = raw_plan.get("architecture", "")
        file_plans_raw = raw_plan.get("file_plans") or raw_plan.get("file_plan_list") or []
        order = raw_plan.get("suggested_order") or []
        raw_frameworks = raw_plan.get("frameworks_used") or raw_plan.get("frameworks") or []
        frameworks_used = [
            str(x).strip() for x in raw_frameworks
            if x is not None and str(x).strip()
        ] if isinstance(raw_frameworks, list) else []

        file_plans: list[FilePlan] = []
        for fp in file_plans_raw:
            if isinstance(fp, dict) and fp.get("path"):
                file_plans.append(
                    FilePlan(
                        path=fp.get("path", ""),
                        purpose=fp.get("purpose", ""),
                        classes=fp.get("classes") or [],
                        interfaces=fp.get("interfaces") or [],
                        functions=fp.get("functions") or [],
                        design_pattern=fp.get("design_pattern", ""),
                        dependencies=fp.get("dependencies") or [],
                    )
                )

        if not order and file_plans:
            order = [fp.path for fp in file_plans]

        planning = PlanningOutput(
            architecture=arch,
            file_plans=file_plans,
            suggested_order=order,
            frameworks_used=frameworks_used if isinstance(frameworks_used, list) else [],
        )
        if stages_dir:
            save_planning_stage(stages_dir, prompt_plan, raw_plan)
        logger.info("规划完成: %d 个文件", len(file_plans))

        return requirement, planning

    def plan_only(
        self, requirement: RequirementOutput, stages_dir: Path | None = None
    ) -> PlanningOutput:
        """当需求已确认（如从聊天传入）时，仅执行规划。"""
        req_json = requirement.model_dump_json(exclude_none=True)
        prompt_plan = PLANNING_PROMPT.format(requirement_json=req_json)
        raw_plan = self.llm.chat_json(
            messages=[{"role": "user", "content": prompt_plan}],
            temperature=0.2,
        )
        arch = raw_plan.get("architecture", "")
        file_plans_raw = raw_plan.get("file_plans") or raw_plan.get("file_plan_list") or []
        order = raw_plan.get("suggested_order") or []
        raw_frameworks = raw_plan.get("frameworks_used") or raw_plan.get("frameworks") or []
        frameworks_used = [
            str(x).strip() for x in raw_frameworks
            if x is not None and str(x).strip()
        ] if isinstance(raw_frameworks, list) else []

        file_plans: list[FilePlan] = []
        for fp in file_plans_raw:
            if isinstance(fp, dict) and fp.get("path"):
                file_plans.append(
                    FilePlan(
                        path=fp.get("path", ""),
                        purpose=fp.get("purpose", ""),
                        classes=fp.get("classes") or [],
                        interfaces=fp.get("interfaces") or [],
                        functions=fp.get("functions") or [],
                        design_pattern=fp.get("design_pattern", ""),
                        dependencies=fp.get("dependencies") or [],
                    )
                )
        if not order and file_plans:
            order = [fp.path for fp in file_plans]

        planning = PlanningOutput(
            architecture=arch,
            file_plans=file_plans,
            suggested_order=order,
            frameworks_used=frameworks_used if isinstance(frameworks_used, list) else [],
        )
        if stages_dir:
            save_planning_stage(stages_dir, prompt_plan, raw_plan)
        logger.info("规划完成: %d 个文件", len(file_plans))
        return planning
