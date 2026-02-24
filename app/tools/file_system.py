"""文件系统工具 - 创建目录和文件"""
import logging
import re
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """清理文件名，移除非法字符"""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "project"


class FileSystemTool:
    """文件系统操作工具"""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = Path(base_dir or settings.output_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_project_dir(self, project_id: str) -> Path:
        """创建项目目录，返回绝对路径"""
        safe_name = _sanitize_filename(project_id)
        project_path = self.base_dir / safe_name
        project_path.mkdir(parents=True, exist_ok=True)
        logger.info("创建项目目录: %s", project_path)
        return project_path.resolve()

    def write_file(self, project_path: Path, relative_path: str, content: str) -> Path:
        """在项目目录下写入文件"""
        full_path = project_path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        logger.info("写入文件: %s (size=%d)", full_path, len(content))
        return full_path

    def create_directory(self, project_path: Path, relative_path: str) -> Path:
        """在项目目录下创建子目录"""
        full_path = project_path / relative_path
        full_path.mkdir(parents=True, exist_ok=True)
        return full_path
