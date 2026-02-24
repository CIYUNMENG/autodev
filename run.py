"""启动入口 - 强制 UTF-8 解决 Windows 中文乱码"""
import os
import subprocess
import sys

# Windows 且未启用 UTF-8 时：用 subprocess 重新启动（execve 在 Windows 上会直接退出导致终端返回）
if sys.platform == "win32" and not getattr(sys.flags, "utf8_mode", False):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    try:
        sys.exit(subprocess.run([sys.executable, "-X", "utf8"] + sys.argv, env=env).returncode)
    except KeyboardInterrupt:
        sys.exit(130)  # 128 + SIGINT，Ctrl+C 时干净退出

# 当前进程控制台 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],
    )
