"""Skill 加载与注册 - 兼容 ClawHub/OpenClaw 格式，支持从 skills/ 目录加载"""
from app.skills.loader import list_skills, load_skills
from app.skills.registry import get_all_instructions, get_skill, Skill

__all__ = [
    "Skill",
    "get_skill",
    "list_skills",
    "load_skills",
    "get_all_instructions",
]
