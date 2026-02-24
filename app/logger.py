"""统一日志配置 - 支持控制台与文件持久化，便于排查问题"""
import io
import logging
import sys
from pathlib import Path
from typing import Any

from app.config import settings


class UTF8StreamHandler(logging.StreamHandler):
    """强制 UTF-8 输出的 StreamHandler，解决 uvicorn worker 在 Windows 下中文乱码"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            stream = self.stream
            if isinstance(stream, io.TextIOBase):
                # 直接写 buffer 避免 TextIOWrapper 的默认编码
                buf = getattr(stream, "buffer", None)
                if buf is not None:
                    buf.write(msg.encode("utf-8", errors="replace"))
                    buf.write(self.terminator.encode("utf-8"))
                    buf.flush()
                    return
            stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def setup_file_logging() -> None:
    """
    将日志写入文件 logs/autodev.log，与控制台同时输出。
    便于排查卡住、超时等问题：tail -f logs/autodev.log 即可实时查看进度。
    """
    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "autodev.log"

    root = logging.getLogger()
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # utf-8-sig 带 BOM，Windows 记事本等能正确识别 UTF-8
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    # 文件日志使用 DEBUG 以记录更多操作，控制台仍为 INFO
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)


def setup_logger(name: str, level: str | None = None) -> logging.Logger:
    """创建带统一格式的 logger"""
    log = logging.getLogger(name)
    log.setLevel(getattr(logging, level or settings.log_level, logging.INFO))
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        log.addHandler(h)
    return log


def log_step(
    logger: logging.Logger,
    phase: str,
    message: str,
    project_id: str | None = None,
    **kwargs: Any,
) -> None:
    """记录阶段步骤，支持 project_id 便于异步任务追踪"""
    prefix = f"[{project_id}] " if project_id else ""
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    full = f"{prefix}[{phase}] {message}"
    if extra:
        full = f"{full} {extra}"
    logger.info("%s", full)
