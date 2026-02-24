"""需求分析输出结构"""
from pydantic import BaseModel, Field


class RequirementOutput(BaseModel):
    """需求分析 Agent 的输出结构"""

    project_type: str = Field(..., description="项目类型，如 web_app, cli_tool, api_service, native_app")
    programming_language: str = Field(
        default="python",
        description="编程语言，如 python, cpp, javascript, java",
    )
    target_users: str = Field(..., description="目标用户描述")
    core_features: list[str] = Field(default_factory=list, description="核心功能列表")
    non_functional_requirements: list[str] = Field(
        default_factory=list, description="非功能需求"
    )
    # 信息充分性
    is_sufficient: bool = Field(True, description="信息是否足以生成完整项目")
    missing_info: list[str] = Field(default_factory=list, description="缺失的关键信息")
    assumptions: list[str] = Field(default_factory=list, description="基于假设补充的内容")
