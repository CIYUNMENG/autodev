"""聊天式需求收集 API"""
import json
import threading
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agents import RequirementAgent
from app.agents.requirement import REQUIREMENT_PROMPT
from app.chat_store import ChatSession, ChatMessage, create_session, get_session, update_session
from app.llm import LLMClient
from app.orchestrator import Orchestrator
from app.schemas.state import TaskPhase, TaskState
from app.task_store import get_task, set_task

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _build_topic_from_messages(messages: list[ChatMessage]) -> str:
    parts = []
    for m in messages:
        if m.role == "user":
            parts.append(m.content.strip())
    return "\n\n补充说明：".join(parts) if len(parts) > 1 else (parts[0] if parts else "")


def _run_and_store(task_id: str, topic: str, requirement: dict | None = None) -> None:
    try:
        def on_update(s: TaskState) -> None:
            set_task(task_id, s)

        state = Orchestrator().run(topic, on_state_update=on_update, requirement=requirement)
        set_task(task_id, state)
    except Exception:
        import traceback
        traceback.print_exc()


async def _parse_json_utf8(request: Request) -> dict:
    body = await request.body()
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("gbk", errors="replace")
    return json.loads(text)


@router.post("/message")
async def chat_message(request: Request):
    """
    发送消息，进行需求分析。
    若需求不充分，返回缺失信息提示，用户可继续补充。
    """
    data = await _parse_json_utf8(request)
    message = (data.get("message") or "").strip()
    session_id = (data.get("session_id") or "").strip()

    if not message:
        return {"error": "message 不能为空"}

    session: ChatSession | None = get_session(session_id) if session_id else None
    if not session:
        session = create_session()
        session_id = session.session_id

    session.messages.append(ChatMessage(role="user", content=message))
    topic = _build_topic_from_messages(session.messages)

    try:
        llm = LLMClient()
        if not llm.is_available:
            return {
                "error": "LLM 未配置，请在 .env 中设置 OPENAI_API_KEY 或 ARK_API_KEY",
                "session_id": session_id,
            }
        req_agent = RequirementAgent(llm)
        requirement = req_agent.analyze(topic)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "error": f"需求分析失败: {e}",
            "session_id": session_id,
            "reply": f"抱歉，分析时出错：{e}",
        }

    session.topic_full = topic
    session.requirement = requirement.model_dump()
    session.is_sufficient = requirement.is_sufficient

    if not requirement.is_sufficient:
        parts = ["需求分析显示信息不足，请补充以下内容："]
        if requirement.missing_info:
            parts.append("\n- " + "\n- ".join(requirement.missing_info))
        if requirement.assumptions:
            parts.append("\n\n当前假设：\n- " + "\n- ".join(requirement.assumptions))
        reply = "".join(parts)
    else:
        summary = [
            f"项目类型：{requirement.project_type}",
            f"编程语言：{requirement.programming_language}",
            f"目标用户：{requirement.target_users}",
            f"核心功能：{', '.join(requirement.core_features[:5])}{'...' if len(requirement.core_features) > 5 else ''}",
        ]
        reply = "需求已明确！\n\n" + "\n".join(summary) + "\n\n可以点击「开始生成」创建项目。"

    session.messages.append(ChatMessage(role="assistant", content=reply))

    return {
        "session_id": session_id,
        "reply": reply,
        "is_sufficient": requirement.is_sufficient,
        "missing_info": requirement.missing_info,
        "requirement": session.requirement,
    }


def _sse_event(event: str, data: str | dict) -> str:
    """构建 SSE 事件"""
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


def _stream_message_gen(
    message: str,
    session_id: str,
):
    """流式消息生成器（同步）：先 yield 文本块，结束时 yield done 事件。FastAPI 会在线程池中运行。"""
    session: ChatSession | None = get_session(session_id) if session_id else None
    if not session:
        session = create_session()
        session_id = session.session_id

    session.messages.append(ChatMessage(role="user", content=message))
    topic = _build_topic_from_messages(session.messages)
    prompt = REQUIREMENT_PROMPT.format(topic=topic)
    buffer: list[str] = []

    try:
        llm = LLMClient()
        if not llm.is_available:
            yield _sse_event("error", {"error": "LLM 未配置"})
            return

        for chunk in llm.chat_stream(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        ):
            buffer.append(chunk)
            yield _sse_event("chunk", {"text": chunk})

        raw_text = "".join(buffer)
        raw = json.loads(raw_text)
        requirement = RequirementAgent.parse_raw(raw)

        session.topic_full = topic
        session.requirement = requirement.model_dump()
        session.is_sufficient = requirement.is_sufficient

        if not requirement.is_sufficient:
            parts = ["需求分析显示信息不足，请补充以下内容："]
            if requirement.missing_info:
                parts.append("\n- " + "\n- ".join(requirement.missing_info))
            if requirement.assumptions:
                parts.append("\n\n当前假设：\n- " + "\n- ".join(requirement.assumptions))
            reply = "".join(parts)
        else:
            summary = [
                f"项目类型：{requirement.project_type}",
                f"编程语言：{requirement.programming_language}",
                f"目标用户：{requirement.target_users}",
                f"核心功能：{', '.join(requirement.core_features[:5])}{'...' if len(requirement.core_features) > 5 else ''}",
            ]
            reply = "需求已明确！\n\n" + "\n".join(summary) + "\n\n可以点击「开始生成」创建项目。"

        session.messages.append(ChatMessage(role="assistant", content=reply))

        yield _sse_event(
            "done",
            {
                "session_id": session_id,
                "reply": reply,
                "is_sufficient": requirement.is_sufficient,
                "missing_info": requirement.missing_info,
                "requirement": session.requirement,
            },
        )
    except json.JSONDecodeError as e:
        reply = f"解析结果失败，请重试。原始输出已展示。\n错误：{e}"
        session.messages.append(ChatMessage(role="assistant", content=reply))
        yield _sse_event(
            "done",
            {
                "session_id": session_id,
                "reply": reply,
                "is_sufficient": False,
                "error": str(e),
            },
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield _sse_event("error", {"error": str(e), "session_id": session_id})


@router.post("/message/stream")
async def chat_message_stream(request: Request):
    """
    流式发送消息，使用 SSE 逐块返回 LLM 输出。
    事件类型：chunk（文本块）、done（完成）、error（错误）。
    """
    data = await _parse_json_utf8(request)
    message = (data.get("message") or "").strip()
    session_id = (data.get("session_id") or "").strip()

    if not message:
        return {"error": "message 不能为空"}

    return StreamingResponse(
        _stream_message_gen(message, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate")
async def chat_generate(request: Request):
    """基于当前会话的需求，开始生成项目（异步）"""
    data = await _parse_json_utf8(request)
    session_id = (data.get("session_id") or "").strip()

    if not session_id:
        return {"error": "session_id 不能为空"}

    session = get_session(session_id)
    if not session:
        return {"error": "会话不存在或已过期"}

    topic = session.topic_full or _build_topic_from_messages(session.messages)
    if not topic.strip():
        return {"error": "请先发送项目描述"}

    task_id = f"task_{uuid.uuid4().hex[:12]}"
    update_session(session_id, task_id=task_id)

    # 立即注册初始状态，避免轮询时「任务不存在」
    initial = TaskState(
        project_id=task_id,
        topic=topic.strip(),
        phase=TaskPhase.REQUIREMENT_ANALYSIS,
    )
    set_task(task_id, initial)

    t = threading.Thread(
        target=_run_and_store,
        args=(task_id, topic.strip(), session.requirement),
        daemon=True,
    )
    t.start()

    return {
        "task_id": task_id,
        "session_id": session_id,
        "message": "生成已启动，正在轮询进度...",
    }


@router.get("/progress/{task_id}")
def chat_get_progress(task_id: str):
    """查询生成进度（复用 task_store）"""
    state = get_task(task_id)
    if not state:
        return {"error": "任务不存在或已完成"}
    return state.model_dump()
