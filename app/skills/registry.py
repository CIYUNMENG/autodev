"""Skill 注册表 - 存储已加载的 skills"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Skill:
    """单个 Skill 的元数据与指令内容"""

    name: str
    description: str = ""
    instructions: str = ""
    version: str = ""
    source_path: str = ""


_skills: dict[str, Skill] = {}


def register(skill: Skill) -> None:
    _skills[skill.name] = skill


def get_skill(name: str) -> Optional[Skill]:
    return _skills.get(name)


def list_skill_names() -> list[str]:
    return list(_skills.keys())


def get_all_instructions() -> str:
    """合并所有 skill 的 instructions，用于注入系统提示"""
    if not _skills:
        return ""
    parts = ["\n\n## 已加载 Skills\n"]
    for name, skill in _skills.items():
        if skill.instructions.strip():
            parts.append(f"### {skill.name}")
            if skill.description:
                parts.append(f"- 描述：{skill.description}")
            parts.append(skill.instructions.strip())
            parts.append("")
    return "\n".join(parts).strip()


def clear() -> None:
    _skills.clear()
