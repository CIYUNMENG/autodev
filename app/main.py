"""FastAPI 应用入口"""
import json
import logging
import os
import sys

# 必须最早执行：强制 UTF-8，避免 worker 进程中文乱码（日志、HTTP、控制台）
os.environ.setdefault("PYTHONUTF8", "1")
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.routes import router
from app.api.chat_routes import router as chat_router
from app.api.tool_routes import router as tool_router
from app.config import settings
from app.logger import setup_file_logging


class UTF8JSONResponse(JSONResponse):
    """强制 UTF-8 编码的 JSON 响应，避免中文乱码"""

    media_type = "application/json; charset=utf-8"

    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")

# 统一日志配置：控制台 + 文件持久化
# 使用 UTF8StreamHandler 避免 uvicorn worker 在 Windows 下中文乱码
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[],
)
from app.logger import UTF8StreamHandler, setup_file_logging

root = logging.getLogger()
root.handlers.clear()
h = UTF8StreamHandler(sys.stdout)
h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
root.addHandler(h)
setup_file_logging()  # 写入 logs/autodev.log，便于排查卡住/超时

app = FastAPI(
    title="AutoDev Agent",
    description="自主软件工程生成系统 - 输入项目主题，自动完成需求分析、代码生成",
    version="0.1.0",
    default_response_class=UTF8JSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(chat_router)
app.include_router(tool_router)

# 可选：挂载 MCP 服务（需 pip install mcp[cli]），供 Cursor/Claude 等客户端调用
# 若出现页面一直转圈，可暂时设为 False 排除 MCP 影响
_enable_mcp = os.environ.get("AUTODEV_ENABLE_MCP", "1") == "1"
# 加载 skills 目录下的技能（ClawHub/Cursor 格式）
try:
    from app.skills import load_skills
    n = load_skills()
    if n > 0:
        logging.getLogger(__name__).info("已加载 %d 个 skill", n)
except Exception as e:
    logging.getLogger(__name__).debug("Skills 加载: %s", e)

if _enable_mcp:
    try:
        from app.mcp_server import create_mcp_app
        mcp_app = create_mcp_app()
        if mcp_app is not None:
            app.mount("/mcp", mcp_app)
    except Exception as e:
        logging.getLogger(__name__).debug("MCP 未挂载: %s", e)


@app.get("/chat")
def chat_page():
    """聊天式项目生成页面"""
    path = Path(__file__).parent / "static" / "chat.html"
    return FileResponse(path, media_type="text/html; charset=utf-8")


@app.get("/dashboard")
def dashboard_page():
    """任务仪表盘页面"""
    path = Path(__file__).parent / "static" / "dashboard.html"
    return FileResponse(path, media_type="text/html; charset=utf-8")


@app.get("/")
def root():
    return {
        "service": "AutoDev Agent",
        "version": "0.1.0",
        "docs": "/docs",
        "chat": "/chat",
        "dashboard": "/dashboard",
        "api": "POST /api/generate  Body: {\"topic\": \"你的项目主题\"}",
        "tools": "GET /api/tools   POST /api/tools/generate_project",
        "mcp": "若已安装 mcp，MCP 端点: /mcp",
    }
