"""Agent 编排器 - 协调需求分析 → 规划 → 代码生成"""
import logging
import uuid
from typing import Callable
from datetime import datetime
from pathlib import Path

from app.agents import RequirementPlanningToolAgent, CodegenToolAgent
from app.llm import LLMClient
from app.logger import log_step
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
        self.req_plan_agent = RequirementPlanningToolAgent(self.llm)
        self.codegen_agent = CodegenToolAgent(self.llm, self.fs)

    def run(
        self,
        topic: str,
        on_state_update: "Callable[[TaskState], None] | None" = None,
        requirement: RequirementOutput | None = None,
        project_id: str | None = None,
    ) -> TaskState:
        """
        执行完整流程：需求分析 → 规划 → 代码生成
        on_state_update: 可选，状态更新时回调，用于异步进度推送
        requirement: 可选，已确认的需求（如从聊天传入），传入则跳过需求分析直接规划
        project_id: 可选，指定项目 ID（与 task_id 一致），用于任务查询与输出目录命名
        返回最终任务状态
        """
        def _notify() -> None:
            if on_state_update:
                on_state_update(state)
        project_id = project_id or f"proj_{uuid.uuid4().hex[:12]}"
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

            # Phase 1: RequirementPlanningToolAgent（需求分析 + 规划）
            if requirement is not None:
                requirement = RequirementOutput.model_validate(requirement) if isinstance(requirement, dict) else requirement
                state.requirement = requirement.model_dump()
                state.completed_steps.append("requirement_analysis")
                from app.stages import save_requirement_stage
                save_requirement_stage(stages_dir, f"# 聊天中已确认的需求\n\n{topic}", requirement.model_dump())
                log_step(logger, "requirement", "使用已确认需求，跳过分析", project_id=project_id)
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
                planning = self.req_plan_agent.plan_only(requirement, stages_dir=stages_dir)
            else:
                state.phase = TaskPhase.REQUIREMENT_ANALYSIS
                state.updated_at = datetime.now()
                log_step(logger, "req_plan", "RequirementPlanningToolAgent 开始", project_id=project_id, topic=topic[:50])
                requirement, planning = self.req_plan_agent.analyze_and_plan(topic, stages_dir=stages_dir)
                if not requirement.is_sufficient:
                    state.phase = TaskPhase.REQUIREMENT_INSUFFICIENT
                    state.error_log.append({
                        "step": "requirement",
                        "error": "信息不足",
                        "missing_info": requirement.missing_info,
                    })
                    state.updated_at = datetime.now()
                    return state

            state.planning = planning.model_dump()
            state.progress.total_files = len(planning.file_plans)
            log_step(logger, "planning", "规划完成", project_id=project_id, files=len(planning.file_plans))
            state.completed_steps.append("planning")
            _notify()

            if not planning.file_plans:
                state.phase = TaskPhase.FAILED
                state.error_log.append({
                    "step": "planning",
                    "error": "规划结果为空，请重试或检查需求",
                })
                state.updated_at = datetime.now()
                log_step(logger, "planning", "规划为空，任务失败", project_id=project_id)
                return state

            # Phase 3: 代码生成
            state.phase = TaskPhase.CODE_GENERATION
            state.updated_at = datetime.now()

            def on_progress(path: str, done: int, total: int) -> None:
                state.progress.current_step = path
                state.progress.completed_files = done
                state.updated_at = datetime.now()
                log_step(logger, "codegen", "生成进度", project_id=project_id, file=path, done=done, total=total)
                _notify()

            created, failed = self.codegen_agent.generate_from_plan(
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
