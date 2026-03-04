"""工具 Agent - 按 FilePlan 生成代码，供主 Agent / Orchestrator 调用（非 MCP 工具）"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from app.agents.base import AgentCapabilities, ToolAgentBase
from app.agents.reflection import reflect_on_error
from app.framework_constraints import (
    FRAMEWORK_CONSTRAINTS,
    get_constraints_for_frameworks,
)
from app.llm import LLMClient
from app.schemas.planning import FilePlan, PlanningOutput
from app.schemas.requirement import RequirementOutput
from app.stages import save_codegen_stage
from app.tools import FileSystemTool

logger = logging.getLogger(__name__)


def _infer_frameworks(planning: PlanningOutput) -> list[str]:
    """当 planning.frameworks_used 为空时，从 file_plans 的 path/purpose/classes 推断使用的框架。"""
    keywords: list[tuple[str, str]] = [
        ("pyqt5", "PyQt5"),
        ("pyqt6", "PyQt6"),
        ("pyqt", "PyQt5"),
        ("qt5", "PyQt5"),
        ("qt6", "PyQt6"),
        ("tkinter", "tkinter"),
        ("tk ", "tkinter"),
    ]
    found: set[str] = set()
    text_parts: list[str] = []
    for fp in planning.file_plans:
        text_parts.append(fp.path)
        text_parts.append(fp.purpose)
        text_parts.extend(fp.classes)
    combined = " ".join(text_parts).lower()
    for kw, fw in keywords:
        if fw in FRAMEWORK_CONSTRAINTS and kw in combined and fw not in found:
            found.add(fw)
    return list(found)


SINGLE_FILE_PROMPT = """你是一个专业的软件工程师。根据需求、规划和当前文件的规划，生成该文件的完整代码。

## 需求摘要
- 项目类型: {project_type}
- 编程语言: {programming_language}
- 核心功能: {core_features}

## 整体架构
{architecture}

## 当前文件规划
- 路径: {file_path}
- 职责: {purpose}
- 类: {classes}
- 接口: {interfaces}
- 函数: {functions}
- 设计模式: {design_pattern}
- 依赖文件: {dependencies}

## 已有依赖文件内容（供参考）
{existing_files_context}

## 框架与 API 约束（必须遵守）
{framework_constraints}

## 要求
1. 使用 {programming_language} 实现
2. 字符串字面量中换行用 \\n 转义，禁止引号内字面换行
3. 只输出该文件的完整代码，不要 JSON 包裹，不要 markdown 代码块，不要解释文字
4. 直接输出可运行的代码
5. **接口契约**：若 classes 描述中明确要求定义信号（如 PyQt 的 button_clicked、action_triggered 等）或方法，必须在实现中完整定义并在相应事件发生时正确发射/调用，否则依赖本文件的其他文件将无法运行
"""

REFLECT_RETRY_SUFFIX = """

---
## [反思重试] 上一次生成失败，请根据以下信息修正后重新生成

**失败原因**: {error}

**批评者建议**: {suggestion}

请严格遵循上述建议，重新生成该文件的完整代码。只输出代码，不要解释。"""


def _topological_levels(file_plans: list[FilePlan]) -> list[list[str]]:
    """按依赖关系分层，每层内可并行"""
    path_to_plan = {fp.path: fp for fp in file_plans}
    remaining = set(path_to_plan.keys())
    levels: list[list[str]] = []
    while remaining:
        level = [
            p for p in remaining
            if all(dep not in remaining for dep in path_to_plan[p].dependencies)
        ]
        if not level:
            level = list(remaining)
        levels.append(level)
        remaining -= set(level)
    return levels


class CodegenToolAgent(ToolAgentBase):
    """
    代码生成工具 Agent：按 FilePlan 生成代码，支持并发与反思重试。
    供 Orchestrator 调用，内部组件，不是 MCP 工具。
    MCP 工具是 generate_project、get_progress，由 mcp_server 暴露。
    """

    capabilities = AgentCapabilities(is_tool_agent=True, has_tools=True, has_reflection=True)

    def __init__(self, llm: LLMClient, fs_tool: FileSystemTool):
        super().__init__()
        self.llm = llm
        self.fs = fs_tool

    def _generate_one(
        self,
        fp: FilePlan,
        requirement: RequirementOutput,
        planning: PlanningOutput,
        existing_contents: dict[str, str],
        stages_dir: Path | None = None,
        max_reflect_retries: int = 1,
    ) -> tuple[str, str]:
        """生成单个文件，返回 (path, content)，失败则 raise。支持反思重试。"""
        context_parts = []
        for dep in fp.dependencies:
            if dep in existing_contents:
                context_parts.append(f"### {dep}\n```\n{existing_contents[dep][:2000]}\n```")
        existing_context = "\n\n".join(context_parts) if context_parts else "（无）"

        frameworks = getattr(planning, "frameworks_used", []) or []
        if not frameworks:
            frameworks = _infer_frameworks(planning)
        framework_constraints = get_constraints_for_frameworks(frameworks)

        prompt = SINGLE_FILE_PROMPT.format(
            project_type=requirement.project_type,
            programming_language=requirement.programming_language,
            core_features=json.dumps(requirement.core_features, ensure_ascii=False),
            architecture=planning.architecture,
            file_path=fp.path,
            purpose=fp.purpose,
            classes=json.dumps(fp.classes, ensure_ascii=False),
            interfaces=json.dumps(fp.interfaces, ensure_ascii=False),
            functions=json.dumps(fp.functions, ensure_ascii=False),
            design_pattern=fp.design_pattern,
            dependencies=json.dumps(fp.dependencies, ensure_ascii=False),
            existing_files_context=existing_context,
            framework_constraints=framework_constraints,
        )

        last_error: str | None = None
        for attempt in range(max_reflect_retries + 1):
            try:
                current_prompt = prompt
                if attempt > 0 and last_error:
                    suggestion = reflect_on_error(
                        self.llm,
                        last_error,
                        fp.path,
                        context={"attempt": attempt, "prompt_len": len(prompt)},
                    )
                    current_prompt = prompt + "\n\n" + REFLECT_RETRY_SUFFIX.format(
                        error=last_error,
                        suggestion=suggestion or "（无具体建议）",
                    )
                    logger.info("CodegenToolAgent 反思重试 %s (第 %d 次)", fp.path, attempt + 1)

                logger.info("CodegenToolAgent 生成文件: %s", fp.path)
                raw = self.llm.chat(
                    messages=[{"role": "user", "content": current_prompt}],
                    response_format=None,
                    temperature=0.2,
                    max_tokens=8192,
                )
                if not raw or not isinstance(raw, str):
                    raw = str(raw or "")
                content = raw.strip()
                if content.startswith("```"):
                    lines = content.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    content = "\n".join(lines)
                if stages_dir:
                    save_codegen_stage(stages_dir, fp.path, current_prompt, content)
                return fp.path, content
            except Exception as e:
                last_error = str(e)
                logger.warning("生成失败 %s (attempt %d): %s", fp.path, attempt + 1, last_error)
                if attempt >= max_reflect_retries:
                    raise
        raise RuntimeError(last_error or "生成失败")

    def generate_from_plan(
        self,
        project_path: Path,
        requirement: RequirementOutput,
        planning: PlanningOutput,
        progress_callback: Callable[[str, int, int], None] | None = None,
        max_workers: int = 3,
        stages_dir: Path | None = None,
    ) -> tuple[list[str], list[str]]:
        """
        按规划生成所有文件，支持并发
        返回 (created_paths, failed_paths)
        """
        path_to_plan = {fp.path: fp for fp in planning.file_plans}
        levels = _topological_levels(planning.file_plans)
        total = sum(len(lev) for lev in levels)
        done = 0
        existing: dict[str, str] = {}
        created: list[str] = []
        failed: list[str] = []

        for level_paths in levels:
            plans = [path_to_plan[p] for p in level_paths if p in path_to_plan]
            if max_workers <= 1:
                for fp in plans:
                    try:
                        path, content = self._generate_one(
                            fp, requirement, planning, existing, stages_dir
                        )
                        self.fs.write_file(project_path, path, content)
                        existing[path] = content
                        created.append(path)
                        done += 1
                        if progress_callback:
                            progress_callback(path, done, total)
                        logger.info("生成完成: %s (%d/%d)", path, done, total)
                    except Exception as e:
                        logger.exception("生成失败 %s: %s", fp.path, e)
                        failed.append(fp.path)
                        done += 1
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    futures = {
                        ex.submit(
                            self._generate_one,
                            fp,
                            requirement,
                            planning,
                            dict(existing),
                            stages_dir,
                        ): fp
                        for fp in plans
                    }
                    for future in as_completed(futures):
                        fp = futures[future]
                        try:
                            path, content = future.result()
                            self.fs.write_file(project_path, path, content)
                            existing[path] = content
                            created.append(path)
                            done += 1
                            if progress_callback:
                                progress_callback(path, done, total)
                            logger.info("生成完成: %s (%d/%d)", path, done, total)
                        except Exception as e:
                            logger.exception("生成失败 %s: %s", fp.path, e)
                            failed.append(fp.path)
                            done += 1

        return created, failed
