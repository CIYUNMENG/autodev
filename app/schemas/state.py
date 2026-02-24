"""任务状态结构"""
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskPhase(str, Enum):
    """任务阶段"""

    INIT = "init"
    REQUIREMENT_ANALYSIS = "requirement_analysis"
    REQUIREMENT_INSUFFICIENT = "requirement_insufficient"
    PLANNING = "planning"
    CODE_GENERATION = "code_generation"
    COMPLETED = "completed"
    FAILED = "failed"


class ProgressInfo(BaseModel):
    """进度信息"""

    current_step: str = Field("", description="当前步骤描述")
    total_files: int = Field(0, description="总文件数")
    completed_files: int = Field(0, description="已完成数")
    failed_files: list[str] = Field(default_factory=list, description="失败的文件")


class TaskState(BaseModel):
    """任务状态机状态"""

    project_id: str = Field(..., description="项目 ID")
    topic: str = Field(..., description="用户输入的项目主题")
    phase: TaskPhase = Field(default=TaskPhase.INIT, description="当前阶段")
    requirement: dict[str, Any] | None = Field(default=None, description="需求分析结果")
    planning: dict[str, Any] | None = Field(default=None, description="规划结果")
    progress: ProgressInfo = Field(default_factory=ProgressInfo, description="进度")
    completed_steps: list[str] = Field(default_factory=list, description="已完成步骤")
    error_log: list[dict[str, Any]] = Field(default_factory=list, description="错误记录")
    output_path: str | None = Field(default=None, description="生成项目输出路径")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
