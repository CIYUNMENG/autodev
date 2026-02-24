"""代码生成 Agent - 根据需求使用 LLM 生成实际项目代码"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from app.llm import LLMClient
from app.schemas.requirement import RequirementOutput
from app.stages import save_legacy_codegen_stage
from app.tools import FileSystemTool

logger = logging.getLogger(__name__)

CODEGEN_PROMPT = """你是一个专业的软件工程师。根据以下结构化需求，生成完整的、可直接运行的项目代码。

## 需求文档
- 项目类型: {project_type}
- 编程语言: {programming_language}
- 目标用户: {target_users}
- 核心功能: {core_features}
- 非功能需求: {non_functional_requirements}

## 要求
1. **必须使用指定的编程语言** {programming_language}，不得使用其他语言
2. **必须实现上述核心功能**，不能只写空壳或占位符
3. 项目结构完整：包含入口文件、依赖声明（如 requirements.txt / package.json / CMakeLists.txt / go.mod 等）、README
4. 代码可直接编译/运行
5. **代码规范**：在 Python/JS 等语言的字符串字面量中，换行必须用 `\\n` 转义，禁止在引号内使用字面换行（否则会语法错误）。例如用 `"line1\\nline2"` 而非多行字符串

## 输出格式
必须输出合法 JSON，且只包含一个 JSON 对象，格式如下：
```json
{{
  "files": [
    {{"path": "相对路径/文件名", "content": "文件完整内容"}},
    ...
  ]
}}
```

- path: 相对于项目根目录的路径，如 main.cpp、src/calc.h、README.md
- content: 文件的完整内容，字符串内换行用 \\n 表示

请直接输出 JSON，不要包含 markdown 代码块包裹或其它解释文字。"""


def _parse_llm_output(text: str) -> list[dict[str, str]]:
    """解析 LLM 输出的 JSON，提取 files 列表"""
    if not text or not isinstance(text, str):
        return []
    # 去除 BOM、null 字节及首尾空白
    text = text.replace("\x00", "").strip().lstrip("\ufeff")
    # 若已是纯 JSON（以 { 开头），直接解析，不做 markdown 提取
    # 否则 content 中的 ``` 会干扰 markdown 提取，破坏 JSON
    if not text.strip().startswith("{"):
        if "```" in text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if match:
                text = match.group(1).strip()
        start = text.find("{")
        if start > 0:
            text = text[start:]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("LLM 输出 JSON 解析失败: %s，尝试从截断内容恢复", e)
        # 截断时尝试提取已完整的 files 项
        files = _extract_files_from_truncated(text)
        return files if files else []

    files = data.get("files") or data.get("file_list") or []
    if not isinstance(files, list):
        return []
    return [f for f in files if isinstance(f, dict) and f.get("path") and f.get("content") is not None]


def _save_llm_debug(project_path: Path, messages: list, raw_response: str) -> Path:
    """将 LLM 完整请求和响应保存到文件，便于调试，返回 response 文件路径"""
    debug_dir = project_path / "_llm_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    request_path = debug_dir / f"request_{ts}.json"
    response_path = debug_dir / f"response_{ts}.txt"
    request_data = {
        "timestamp": datetime.now().isoformat(),
        "messages": messages,
        "params": {"temperature": 0.2, "max_tokens": 16384},
    }
    request_path.write_text(json.dumps(request_data, ensure_ascii=False, indent=2), encoding="utf-8")
    response_path.write_text(raw_response or "(空)", encoding="utf-8")
    logger.info("LLM 调试信息已保存: %s", debug_dir)
    return response_path


def _extract_files_from_truncated(text: str) -> list[dict[str, str]]:
    """从可能被截断的 JSON 中尝试提取 files 项"""
    result: list[dict[str, str]] = []
    # 匹配 "path": "xxx", "content": "yyy" 或 "path":"xxx","content":"yyy"
    pattern = re.compile(
        r'"path"\s*:\s*"([^"]*)"\s*,\s*"content"\s*:\s*"((?:[^"\\]|\\.)*)"',
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        path = m.group(1).strip()
        content = m.group(2)
        if path and path not in [r["path"] for r in result]:
            content = content.replace("\\n", "\n").replace('\\"', '"')
            result.append({"path": path, "content": content})
    return result


class CodegenAgent:
    """代码生成 Agent - 使用 LLM 根据需求生成实际代码"""

    def __init__(self, llm: LLMClient, fs_tool: FileSystemTool):
        self.llm = llm
        self.fs = fs_tool

    def generate(
        self,
        project_path: Path,
        requirement: RequirementOutput,
        stages_dir: Path | None = None,
    ) -> list[str]:
        """
        根据需求在指定目录生成项目
        返回创建的文件路径列表
        """
        logger.info(
            "代码生成开始: path=%s, language=%s",
            project_path,
            requirement.programming_language,
        )

        prompt = CODEGEN_PROMPT.format(
            project_type=requirement.project_type,
            programming_language=requirement.programming_language,
            target_users=requirement.target_users,
            core_features=json.dumps(requirement.core_features, ensure_ascii=False),
            non_functional_requirements=json.dumps(
                requirement.non_functional_requirements, ensure_ascii=False
            ),
        )

        messages = [{"role": "user", "content": prompt}]
        try:
            raw = self.llm.chat(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=16384,  # 代码生成需较长输出，避免截断
            )
        except Exception as e:
            logger.exception("LLM 代码生成失败: %s", e)
            raise

        # 确保 raw 为 str（部分 API 可能返回 bytes）
        if raw is not None and not isinstance(raw, str):
            raw = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        raw = raw or ""

        # 保存到 _stages 便于查看各阶段输入输出
        if stages_dir:
            save_legacy_codegen_stage(stages_dir, prompt, raw)
            response_path = stages_dir / "codegen_legacy_output.txt"
        else:
            response_path = _save_llm_debug(project_path, messages, raw)

        files = _parse_llm_output(raw)
        # 若内存中解析失败，尝试从保存的文件读取（解决 API 返回与保存内容编码差异）
        if not files and response_path and response_path.exists():
            logger.warning("从内存解析失败，尝试从保存的 response 文件解析")
            raw_from_file = response_path.read_text(encoding="utf-8")
            files = _parse_llm_output(raw_from_file)
        if not files:
            raise RuntimeError(
                "LLM 未返回有效文件列表，请检查模型输出格式。原始输出前 500 字符: "
                + (str(raw)[:500] if raw else "(空)")
            )

        created: list[str] = []
        for item in files:
            rel_path = item["path"].strip().lstrip("/")
            content = item["content"]
            if isinstance(content, str) and "\\n" in content:
                content = content.replace("\\n", "\n")
            self.fs.write_file(project_path, rel_path, str(content))
            created.append(rel_path)

        # 追加生成日志
        log_content = f"""# AutoDev Agent 生成日志

## 需求摘要
- 项目类型: {requirement.project_type}
- 编程语言: {requirement.programming_language}
- 目标用户: {requirement.target_users}
- 核心功能: {requirement.core_features}

## 已生成文件
{chr(10).join('- ' + p for p in created)}
"""
        self.fs.write_file(project_path, "AUTODEV_LOG.md", log_content)
        created.append("AUTODEV_LOG.md")

        logger.info("代码生成完成: files=%s", created)
        return created
