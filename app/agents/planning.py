"""规划 Agent - 将需求拆分为文件级规划"""
import json
import logging
from pathlib import Path
from typing import Any

from app.llm import LLMClient
from app.schemas.planning import FilePlan, PlanningOutput
from app.schemas.requirement import RequirementOutput
from app.stages import save_planning_stage

logger = logging.getLogger(__name__)

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


class PlanningAgent:
    """规划 Agent"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def plan(self, requirement: RequirementOutput, stages_dir: Path | None = None) -> PlanningOutput:
        """根据需求生成文件级规划。stages_dir 不为空时保存输入输出到该目录"""
        logger.info("规划开始: project_type=%s", requirement.project_type)

        req_json = requirement.model_dump_json(exclude_none=True)
        prompt = PLANNING_PROMPT.format(requirement_json=req_json)

        raw = self.llm.chat_json(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )

        # 解析并校验
        arch = raw.get("architecture", "")
        file_plans_raw = raw.get("file_plans") or raw.get("file_plan_list") or []
        order = raw.get("suggested_order") or []
        raw_frameworks = raw.get("frameworks_used") or raw.get("frameworks") or []
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

        result = PlanningOutput(
            architecture=arch,
            file_plans=file_plans,
            suggested_order=order,
            frameworks_used=frameworks_used if isinstance(frameworks_used, list) else [],
        )
        if stages_dir:
            save_planning_stage(stages_dir, prompt, raw)
        logger.info("规划完成: %d 个文件", len(file_plans))
        return result
