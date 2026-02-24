"""验证 LLM response 文件能否正确解析"""
import json
import sys
from pathlib import Path

def main():
    # 默认使用最近的 response 文件
    debug_dir = Path(__file__).parent.parent / "generated_projects"
    response_files = list(debug_dir.glob("*/_llm_debug/response_*.txt"))
    if not response_files:
        print("未找到 response 文件")
        sys.exit(1)
    
    # 使用最新的
    latest = max(response_files, key=lambda p: p.stat().st_mtime)
    print(f"验证: {latest}")
    
    try:
        raw = latest.read_text(encoding="utf-8")
        text = raw.replace("\x00", "").strip().lstrip("\ufeff")
        data = json.loads(text)
        files = data.get("files", [])
        print(f"解析成功: {len(files)} 个文件")
        for f in files:
            print(f"  - {f.get('path', '?')}")
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
