"""各阶段 LLM 输入输出存储 - 保存到项目 _stages 目录"""
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    """将路径转为安全文件名"""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "file"


def save_requirement_stage(stages_dir: Path, prompt: str, output: dict) -> None:
    """保存需求分析阶段的输入和输出"""
    if not stages_dir:
        return
    stages_dir.mkdir(parents=True, exist_ok=True)
    (stages_dir / "requirement_input.txt").write_text(prompt, encoding="utf-8")
    (stages_dir / "requirement_output.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("已保存需求分析阶段: %s", stages_dir)


def save_planning_stage(stages_dir: Path, prompt: str, output: dict) -> None:
    """保存规划阶段的输入和输出"""
    if not stages_dir:
        return
    stages_dir.mkdir(parents=True, exist_ok=True)
    (stages_dir / "planning_input.txt").write_text(prompt, encoding="utf-8")
    (stages_dir / "planning_output.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("已保存规划阶段: %s", stages_dir)


def save_codegen_stage(stages_dir: Path, file_path: str, prompt: str, output: str) -> None:
    """保存单个文件代码生成的输入和输出"""
    if not stages_dir:
        return
    stages_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(file_path.replace("/", "_").replace("\\", "_"))
    (stages_dir / f"codegen_{safe}_input.txt").write_text(prompt, encoding="utf-8")
    (stages_dir / f"codegen_{safe}_output.txt").write_text(output, encoding="utf-8")
    logger.info("已保存代码生成阶段: %s -> %s", file_path, stages_dir)

