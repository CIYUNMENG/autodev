"""Agent 编排器 - 协调需求分析 → 规划 → 代码生成"""
import logging
import uuid
from typing import Callable
from datetime import datetime
from pathlib import Path

from app.agents import CodegenAgent, FileCodegenAgent, PlanningAgent, RequirementAgent
from app.llm import LLMClient
from app.logger import log_step
from app.config import settings
from app.schemas.requirement import RequirementOutput
from app.schemas.state import TaskPhase, TaskState
from app.tools import FileSystemTool

logger = logging.getLogger(__name__)


def _write_autodev_log(project_path: Path, requirement: RequirementOutput, state: TaskState) -> None:
    """写入生成日志"""
    from app.tools import FileSystemTool
    fs = FileSystemTool()
    files_list = [s for s in state.completed_steps if '.' in s and s not in ('requirement_analysis', 'planning', 'code_generation')]
    content = f"""# AutoDev Agent 生成日志

## 需求摘要
- 项目类型: {requirement.project_type}
- 编程语言: {requirement.programming_language}
- 目标用户: {requirement.target_users}
- 核心功能: {requirement.core_features}

## 各阶段输入输出
见 `_stages/` 目录：
- requirement_input.txt / requirement_output.json - 需求分析
- planning_input.txt / planning_output.json - 规划
- codegen_<文件>_input.txt / _output.txt - 各文件代码生成

## 已生成文件
{chr(10).join('- ' + s for s in files_list)}
"""
    fs.write_file(project_path, "AUTODEV_LOG.md", content)


class Orchestrator:
    """编排：需求分析 → 规划 → 代码生成（支持按文件并发）"""

    def __init__(self):
        self.llm = LLMClient()
        self.fs = FileSystemTool()
        self.requirement_agent = RequirementAgent(self.llm)
        self.planning_agent = PlanningAgent(self.llm)
        self.file_codegen_agent = FileCodegenAgent(self.llm, self.fs)
        self.legacy_codegen_agent = CodegenAgent(self.llm, self.fs)

    def run(
        self,
        topic: str,
        on_state_update: "Callable[[TaskState], None] | None" = None,
        requirement: RequirementOutput | None = None,
    ) -> TaskState:
        """
        执行完整流程：需求分析 → 规划 → 代码生成
        on_state_update: 可选，状态更新时回调，用于异步进度推送
        requirement: 可选，已确认的需求（如从聊天传入），传入则跳过需求分析直接规划
        返回最终任务状态
        """
        def _notify() -> None:
            if on_state_update:
                on_state_update(state)
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        state = TaskState(project_id=project_id, topic=topic)
        log_step(logger, "start", "任务开始", project_id=project_id, topic=topic[:50])
        logger.info("[%s] 创建项目目录并初始化 _stages", project_id)

        try:
            _notify()
            project_path = self.fs.create_project_dir(project_id)
            state.output_path = str(project_path)
            stages_dir = project_path / "_stages"
            stages_dir.mkdir(parents=True, exist_ok=True)
            logger.info("[%s] 项目目录: %s, 阶段存储: %s", project_id, project_path, stages_dir)

            # Phase 1: 需求分析（若已传入 requirement 则跳过，直接进入规划）
            if requirement is not None:
                requirement = RequirementOutput.model_validate(requirement) if isinstance(requirement, dict) else requirement
                state.requirement = requirement.model_dump()
                state.completed_steps.append("requirement_analysis")
                # 保存已确认的需求到 _stages 便于追溯
                from app.stages import save_requirement_stage
                save_requirement_stage(stages_dir, f"# 聊天中已确认的需求\n\n{topic}", requirement.model_dump())
                log_step(logger, "requirement", "使用已确认需求，跳过分析", project_id=project_id)
                _notify()
            else:
                state.phase = TaskPhase.REQUIREMENT_ANALYSIS
                state.updated_at = datetime.now()
                log_step(logger, "requirement", "开始需求分析", project_id=project_id, topic=topic[:50])
                requirement = self.requirement_agent.analyze(topic, stages_dir=stages_dir)
                state.requirement = requirement.model_dump()
                state.completed_steps.append("requirement_analysis")
                log_step(logger, "requirement", "需求分析完成", project_id=project_id)
                _notify()

            if not requirement.is_sufficient:
                state.phase = TaskPhase.REQUIREMENT_INSUFFICIENT
                state.error_log.append({
                    "step": "requirement",
                    "error": "信息不足",
                    "missing_info": requirement.missing_info,
                })
                state.updated_at = datetime.now()
                return state

            # Phase 2: 规划（可配置跳过，use_planning=false 时用旧版整体生成，更快）
            state.phase = TaskPhase.PLANNING
            state.updated_at = datetime.now()
            if not getattr(settings, "use_planning", True):
                from app.schemas.planning import PlanningOutput
                planning = PlanningOutput(architecture="legacy", file_plans=[], suggested_order=[])
                state.planning = planning.model_dump()
                state.progress.total_files = 0
                log_step(logger, "planning", "跳过规划，使用整体生成", project_id=project_id)
            else:
                log_step(logger, "planning", "开始规划", project_id=project_id)
                planning = self.planning_agent.plan(requirement, stages_dir=stages_dir)
                state.planning = planning.model_dump()
                state.progress.total_files = len(planning.file_plans)
                log_step(logger, "planning", "规划完成", project_id=project_id, files=len(planning.file_plans))
            state.completed_steps.append("planning")
            _notify()

            # Phase 3: 代码生成
            state.phase = TaskPhase.CODE_GENERATION
            state.updated_at = datetime.now()

            if planning.file_plans:
                def on_progress(path: str, done: int, total: int) -> None:
                    state.progress.current_step = path
                    state.progress.completed_files = done
                    state.updated_at = datetime.now()
                    log_step(logger, "codegen", "生成进度", project_id=project_id, file=path, done=done, total=total)
                    _notify()

                created, failed = self.file_codegen_agent.generate_from_plan(
                    project_path,
                    requirement,
                    planning,
                    progress_callback=on_progress,
                    max_workers=3,
                    stages_dir=stages_dir,
                )
                state.progress.failed_files = failed
                state.completed_steps.extend(created)
                state.completed_steps.append("code_generation")
                if failed:
                    log_step(logger, "codegen", "部分失败", project_id=project_id, failed=failed)
            else:
                log_step(logger, "codegen", "规划为空，回退到整体生成", project_id=project_id)
                created = self.legacy_codegen_agent.generate(
                    project_path, requirement, stages_dir=stages_dir
                )
                state.completed_steps.extend(created)
                state.completed_steps.append("code_generation")
                state.progress.completed_files = len(created)
                state.progress.total_files = len(created)

            # 写入 AUTODEV_LOG
            _write_autodev_log(project_path, requirement, state)

            state.phase = TaskPhase.COMPLETED
            state.updated_at = datetime.now()
            log_step(logger, "completed", "任务完成", project_id=project_id, path=str(project_path))

        except Exception as e:
            logger.exception("[%s] 编排执行失败: %s", project_id, e)
            state.phase = TaskPhase.FAILED
            state.error_log.append({
                "step": state.phase.value,
                "error": str(e),
                "type": type(e).__name__,
            })
            state.updated_at = datetime.now()

        return state
