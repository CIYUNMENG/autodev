"""Skill 加载器 - 以 ClawHub 格式为主（_meta.json + SKILL.md），其他为备选"""
import json
import logging
from pathlib import Path

from app.skills.registry import Skill, clear, register

logger = logging.getLogger(__name__)

# 技能目录：项目根目录下的 skills/
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("读取 %s 失败: %s", path, e)
        return ""


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 YAML frontmatter，返回 (meta, body)"""
    meta: dict = {}
    body = content
    if content.strip().startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            import re
            for line in parts[1].strip().split("\n"):
                m = re.match(r"(\w+):\s*(.+)", line)
                if m:
                    meta[m.group(1)] = m.group(2).strip().strip('"\'')
            body = parts[2].strip()
    return meta, body


def _load_clawhub_skill(dir_path: Path) -> Skill | None:
    """
    ClawHub 主格式：_meta.json + SKILL.md
    skill-name/
      _meta.json   # manifest
      SKILL.md     # AI 指令
    """
    meta_path = dir_path / "_meta.json"
    skill_md_path = dir_path / "SKILL.md"
    if not meta_path.exists() or not skill_md_path.exists():
        return None

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("解析 %s 失败: %s", meta_path, e)
        return None

    name = meta.get("name", meta.get("slug", dir_path.name))
    description = meta.get("description", meta.get("summary", ""))
    instructions = _read_text(skill_md_path)

    return Skill(
        name=name,
        description=description,
        instructions=instructions,
        version=str(meta.get("version", "")),
        source_path=str(dir_path),
    )


def _load_clawhub_legacy_skill(dir_path: Path) -> Skill | None:
    """
    备选格式：claw.json + instructions.md / README.md / SKILL.md
    """
    claw_path = dir_path / "claw.json"
    if not claw_path.exists():
        return None

    try:
        claw = json.loads(claw_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("解析 %s 失败: %s", claw_path, e)
        return None

    name = claw.get("name", dir_path.name)
    description = claw.get("description", "")

    instructions = ""
    for f in ("instructions.md", "README.md", "SKILL.md"):
        p = dir_path / f
        if p.exists():
            instructions = _read_text(p)
            break

    return Skill(
        name=name,
        description=description,
        instructions=instructions,
        version=str(claw.get("version", "")),
        source_path=str(dir_path),
    )


def _load_cursor_skill(file_path: Path) -> Skill | None:
    """
    Cursor 格式：SKILL.md 带 YAML frontmatter
    ---
    name: xxx
    description: xxx
    ---
    # 正文
    """
    content = _read_text(file_path)
    if not content.strip():
        return None

    meta, body = _parse_frontmatter(content)
    name = meta.get("name", file_path.stem)
    description = meta.get("description", "")

    return Skill(
        name=name,
        description=description,
        instructions=body,
        source_path=str(file_path),
    )


def _skill_already_loaded(skill_dir: Path) -> bool:
    """目录是否已作为 ClawHub 格式加载（_meta.json 或 claw.json）"""
    return (skill_dir / "_meta.json").exists() or (skill_dir / "claw.json").exists()


def load_skills(skills_dir: Path | None = None) -> int:
    """
    从 skills/ 目录加载所有 skills，以 ClawHub 为主：
    1. ClawHub 主格式：_meta.json + SKILL.md
    2. ClawHub 备选：claw.json + instructions.md / README.md / SKILL.md
    3. Cursor 备选：根目录或子目录中的 SKILL.md（无 _meta/claw.json 时）
    返回成功加载的数量
    """
    clear()
    base = skills_dir or _SKILLS_DIR
    if not base.exists():
        return 0

    count = 0
    from app.skills.registry import _skills

    # 1. 遍历子目录，ClawHub 主格式（_meta.json + SKILL.md）
    for item in sorted(base.iterdir()):
        if not item.is_dir():
            continue
        skill = _load_clawhub_skill(item)
        if skill:
            register(skill)
            count += 1
            logger.info("已加载 skill: %s (ClawHub)", skill.name)

    # 2. ClawHub 备选格式（claw.json + instructions/README/SKILL.md）
    for item in sorted(base.iterdir()):
        if not item.is_dir():
            continue
        if (item / "_meta.json").exists():
            continue
        skill = _load_clawhub_legacy_skill(item)
        if skill and skill.name not in _skills:
            register(skill)
            count += 1
            logger.info("已加载 skill: %s (ClawHub-legacy)", skill.name)

    # 3. Cursor 备选：SKILL.md 且所在目录非 ClawHub 格式
    for p in sorted(base.rglob("SKILL.md")):
        if _skill_already_loaded(p.parent):
            continue
        skill = _load_cursor_skill(p)
        if skill and skill.name not in _skills:
            register(skill)
            count += 1
            logger.info("已加载 skill: %s (Cursor)", skill.name)

    return count


def list_skills(skills_dir: Path | None = None) -> list[dict]:
    """列出 skills 目录下可发现的 skill（不加载），用于 API 展示"""
    base = skills_dir or _SKILLS_DIR
    result = []
    seen = set()
    if not base.exists():
        return result

    # 1. ClawHub 主格式：_meta.json + SKILL.md
    for item in sorted(base.iterdir()):
        if not item.is_dir():
            continue
        meta_path = item / "_meta.json"
        if meta_path.exists() and (item / "SKILL.md").exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                name = meta.get("name", meta.get("slug", item.name))
                seen.add(name)
                result.append({
                    "name": name,
                    "description": meta.get("description", meta.get("summary", "")),
                    "version": str(meta.get("version", "")),
                    "format": "clawhub",
                })
            except Exception:
                pass

    # 2. ClawHub 备选：claw.json
    for item in sorted(base.iterdir()):
        if not item.is_dir() or (item / "_meta.json").exists():
            continue
        claw_path = item / "claw.json"
        if claw_path.exists():
            try:
                claw = json.loads(claw_path.read_text(encoding="utf-8"))
                name = claw.get("name", item.name)
                if name not in seen:
                    seen.add(name)
                    result.append({
                        "name": name,
                        "description": claw.get("description", ""),
                        "version": str(claw.get("version", "")),
                        "format": "clawhub-legacy",
                    })
            except Exception:
                pass

    # 3. Cursor 备选：SKILL.md 且所在目录无 _meta/claw.json
    for p in base.rglob("SKILL.md"):
        if _skill_already_loaded(p.parent):
            continue
        content = _read_text(p)
        meta, _ = _parse_frontmatter(content)
        name = meta.get("name", p.stem)
        if name not in seen:
            seen.add(name)
            result.append({
                "name": name,
                "description": meta.get("description", ""),
                "format": "cursor",
            })
    return result
