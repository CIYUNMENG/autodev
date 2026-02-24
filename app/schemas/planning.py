"""规划 Agent 输出结构"""
from pydantic import BaseModel, Field


class FilePlan(BaseModel):
    """单个文件的规划"""

    path: str = Field(..., description="文件路径，如 src/models/user.py")
    purpose: str = Field(..., description="文件职责说明")
    classes: list[str] = Field(default_factory=list, description="类名及简要说明")
    interfaces: list[str] = Field(default_factory=list, description="接口或协议")
    functions: list[str] = Field(default_factory=list, description="函数签名及用途")
    design_pattern: str = Field("", description="设计模式，如 Repository, MVC")
    dependencies: list[str] = Field(default_factory=list, description="依赖的其他文件 path")


class PlanningOutput(BaseModel):
    """规划 Agent 的输出"""

    architecture: str = Field(..., description="整体架构描述")
    file_plans: list[FilePlan] = Field(default_factory=list, description="文件级规划列表")
    suggested_order: list[str] = Field(
        default_factory=list, description="建议生成顺序，按依赖拓扑排序"
    )
    frameworks_used: list[str] = Field(
        default_factory=list,
        description="本项目使用的主要框架/库（如 PyQt5、Django），供代码生成阶段应用预置约束",
    )
