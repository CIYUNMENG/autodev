"""聊天 API：AI 自主决策是否调用工具（confirm_requirement、get_progress），生成由用户点击卡片触发"""
import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agent_tools import CHAT_TOOL_NAMES, run as tool_run, to_openai_tools
from app.skills import get_all_instructions
from app.chat_store import (
    ChatSession,
    ChatMessage,
    create_session,
    get_session,
    update_session,
    persist_session,
    list_sessions,
)
from app.llm import LLMClient

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/sessions")
async def chat_list_sessions():
    """列出所有聊天会话，按更新时间降序，供侧边栏展示"""
    return {"sessions": await asyncio.to_thread(list_sessions)}


@router.get("/session/{session_id}")
async def chat_get_session(session_id: str):
    """获取指定会话的完整内容（含消息），用于切换会话时加载"""
    session = await asyncio.to_thread(get_session, session_id)
    if not session:
        return {"error": "会话不存在或已过期"}
    return {
        "session_id": session.session_id,
        "messages": [{"role": m.role, "content": m.content} for m in session.messages],
        "topic_full": session.topic_full,
        "requirement": session.requirement,
        "task_id": session.task_id,
    }

def _build_system_prompt() -> str:
    """聊天专用系统提示：AI 只调用 confirm_requirement 与 get_progress，不调用 generate_project"""
    tools = to_openai_tools(CHAT_TOOL_NAMES)
    tool_desc = ", ".join(t["function"]["name"] for t in tools)
    base = f"""你是一个友好的 AI 助手，可以自然对话，也可以帮用户完成项目生成等任务。
你拥有工具（{tool_desc}），请根据用户意图自行判断是否调用。工具的具体名称、参数、说明由 API 提供。

**重要：需求确认与生成分离**
- 你**不能**直接触发生成。生成由用户在需求卡片上点击「生成」按钮触发。
- 当用户想创建/生成项目时，先追问项目类型（桌面应用/Web/命令行）、编程语言、核心功能等，待用户补充完整。
- 当用户已提供较完整描述（如「Python 桌面科学计算器，支持三角函数」）或明确说「可以了」「需求就这些」时，调用 **confirm_requirement**，将 topic 设为对话中积累的完整需求。调用成功后，用户会收到一张需求卡片，可在卡片上点击「生成」。
- 若用户只说「帮我做一个xxx」等模糊描述，**不要**调用 confirm_requirement，先追问细节。

当用户询问某任务的进度时，调用 get_progress，task_id 从对话中获取。
若用户只是闲聊或提问，直接回复即可。"""
    skills_instructions = get_all_instructions()
    if skills_instructions:
        base += "\n\n" + skills_instructions
    return base


def _build_topic_from_messages(messages: list[ChatMessage]) -> str:
    parts = []
    for m in messages:
        if m.role == "user":
            parts.append(m.content.strip())
    return "\n\n补充说明：".join(parts) if len(parts) > 1 else (parts[0] if parts else "")


def _run_tool_call_loop(session: ChatSession, session_id: str, tools: list) -> tuple[str, dict | None]:
    """
    执行 LLM + tool calling 循环，返回 (文本回复, requirement_card 数据或 None)。
    当 confirm_requirement 成功时，返回 (reply, {session_id, requirement})。
    """
    llm = LLMClient()
    if not llm.is_available:
        return "LLM 未配置，请在 .env 中设置 OPENAI_API_KEY 或 ARK_API_KEY。", None

    messages = [{"role": "system", "content": _build_system_prompt()}]
    for m in session.messages:
        messages.append({"role": m.role, "content": m.content})

    requirement_card: dict | None = None
    max_rounds = 10
    for _ in range(max_rounds):
        content, tool_calls = llm.chat_with_tools(messages, tools, temperature=0.7)
        if tool_calls:
            assistant_msg = {"role": "assistant", "content": content or ""}
            assistant_msg["tool_calls"] = [
                {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                for tc in tool_calls
            ]
            messages.append(assistant_msg)
            for tc in tool_calls:
                name = tc["name"]
                args = tc.get("arguments") or {}
                args["session_id"] = session_id
                result = tool_run(name, **args)
                if name == "confirm_requirement" and result.ok and result.data:
                    requirement_card = {
                        "session_id": result.data.get("session_id", session_id),
                        "requirement": result.data.get("requirement"),
                    }
                def _json_default(o):
                    if isinstance(o, datetime):
                        return o.isoformat()
                    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
                result_str = json.dumps(
                    {"ok": result.ok, "data": result.data, "error": result.error},
                    ensure_ascii=False,
                    default=_json_default,
                )
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})
        else:
            return content or "（无回复）", requirement_card
    return "处理超时，请重试。", requirement_card


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
    发送消息。AI 自主决策：普通对话或调用工具（generate_project、get_progress 等）。
    """
    data = await _parse_json_utf8(request)
    message = (data.get("message") or "").strip()
    session_id = (data.get("session_id") or "").strip()

    if not message:
        return {"error": "message 不能为空"}

    session: ChatSession | None = await asyncio.to_thread(get_session, session_id) if session_id else None
    if not session:
        session = await asyncio.to_thread(create_session)
        session_id = session.session_id

    session.messages.append(ChatMessage(role="user", content=message))
    session.topic_full = _build_topic_from_messages(session.messages)
    await asyncio.to_thread(persist_session, session_id)

    try:
        tools = to_openai_tools(CHAT_TOOL_NAMES)
        reply, requirement_card = await asyncio.to_thread(_run_tool_call_loop, session, session_id, tools)
        session.messages.append(ChatMessage(role="assistant", content=reply))
        await asyncio.to_thread(persist_session, session_id)
        out = {"session_id": session_id, "reply": reply}
        if requirement_card:
            out["requirement_card"] = requirement_card
        return out
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "session_id": session_id,
            "reply": f"抱歉，处理时出错：{e}",
        }


def _sse_event(event: str, data: str | dict) -> str:
    """构建 SSE 事件"""
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


async def _stream_message_gen(
    message: str,
    session_id: str,
):
    """流式消息生成器（异步）：AI 决策是否调用工具，完成后流式输出最终回复。
    当 confirm_requirement 成功时，额外发送 requirement_card 事件。"""
    session: ChatSession | None = await asyncio.to_thread(get_session, session_id) if session_id else None
    if not session:
        session = await asyncio.to_thread(create_session)
        session_id = session.session_id

    session.messages.append(ChatMessage(role="user", content=message))
    session.topic_full = _build_topic_from_messages(session.messages)
    await asyncio.to_thread(persist_session, session_id)

    try:
        tools = to_openai_tools(CHAT_TOOL_NAMES)
        reply, requirement_card = await asyncio.to_thread(_run_tool_call_loop, session, session_id, tools)
        session.messages.append(ChatMessage(role="assistant", content=reply))
        await asyncio.to_thread(persist_session, session_id)
        # 流式输出：按字符或小块 yield 以模拟打字效果
        chunk_size = 2
        for i in range(0, len(reply), chunk_size):
            yield _sse_event("chunk", {"text": reply[i : i + chunk_size]})
        # 若有需求卡片，先发送 requirement_card 再发送 done
        if requirement_card:
            yield _sse_event("requirement_card", requirement_card)
        yield _sse_event(
            "done",
            {"session_id": session_id, "reply": reply},
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield _sse_event("error", {"error": str(e), "session_id": session_id})


@router.post("/message/stream")
async def chat_message_stream(request: Request):
    """
    流式发送消息，使用 SSE 逐块返回 LLM 输出。
    事件类型：chunk（文本块）、requirement_card（需求卡片）、done（完成）、error（错误）。
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
    """基于当前会话的需求，开始生成项目（异步），通过工具层执行"""
    data = await _parse_json_utf8(request)
    session_id = (data.get("session_id") or "").strip()

    if not session_id:
        return {"error": "session_id 不能为空"}

    session = await asyncio.to_thread(get_session, session_id)
    if not session:
        return {"error": "会话不存在或已过期"}

    topic = session.topic_full or _build_topic_from_messages(session.messages)
    if not topic.strip():
        return {"error": "请先发送项目描述"}

    result = await asyncio.to_thread(
        tool_run,
        "generate_project",
        topic=topic.strip(),
        session_id=session_id,
        requirement=session.requirement,
        async_mode=True,
    )
    if not result.ok:
        return {"error": result.error or "生成启动失败", "session_id": session_id}
    task_id = result.data.get("task_id")
    update_session(session_id, task_id=task_id)
    return {
        "task_id": task_id,
        "session_id": session_id,
        "message": "生成已启动，正在轮询进度...",
    }


@router.get("/progress/{task_id}")
async def chat_get_progress(task_id: str):
    """查询生成进度（通过工具层 task_store）"""
    from app.agent_tools import run as tool_run
    result = await asyncio.to_thread(tool_run, "get_progress", task_id=task_id)
    if not result.ok:
        return {"error": result.error}
    return result.data
