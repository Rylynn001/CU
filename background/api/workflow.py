"""
工作流 API
"""
import asyncio
import json
import logging
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any, List

from api.auth import get_current_user
from agents.conversation_agent import ConversationAgent
from agents.graph.workflow import create_conversation_workflow
from openai import AsyncOpenAI
from repositories.workflow_repo import WorkflowRepository
from repositories.generation_repo import get_language_model_info
from config import get_provider_config_by_rfid
from agents.graph.states import ConversationState
from agents.services.workflow_tools import WorkflowTools, session_tasks
from agents.services.chat_assets import load_chat_assets, build_asset_content, asset_previews

router = APIRouter(prefix="/workflow", tags=["workflow"])
logger = logging.getLogger(__name__)


def get_conversation_agent(model_id: int) -> ConversationAgent:
    """按前端选择的模型编号创建对话 Agent。"""
    model_info = get_language_model_info(model_id)
    if not model_info:
        raise HTTPException(
            status_code=404,
            detail=f"未找到语言模型配置（id={model_id}）"
        )

    provider_config = get_provider_config_by_rfid(model_info['rfid'])
    if not provider_config:
        raise HTTPException(
            status_code=500,
            detail=f"未找到模型 {model_info['name']} 的 provider 配置"
        )

    return ConversationAgent(
        api_key=provider_config['api_key'],
        base_url=provider_config['base_url'],
        model=model_info['name'],
        context_window=model_info.get('context_window'),
    )


def _get_llm_client(model_id: int):
    """按模型编号创建 AsyncOpenAI 客户端，供 LangGraph 提示词优化子图使用。"""
    model_info = get_language_model_info(model_id)
    if not model_info:
        return None
    provider_config = get_provider_config_by_rfid(model_info['rfid'])
    if not provider_config:
        return None
    return AsyncOpenAI(api_key=provider_config['api_key'], base_url=provider_config['base_url'])


_GRAPH_NODE_PROGRESS = {
    "intent": "正在分析你的请求…",
    "prompt_enhance": "正在优化提示词…",
    "direct_execute": "准备生成参数…",
    "execute_tool": "正在执行生成任务…",
}


async def _run_conversation_graph(
    request: 'ChatRequest',
    workflow_tools,
    existing_state: Optional[dict],
    user_content: str,
    request_id: str,
    on_progress=None,
    on_delta=None,
) -> dict:
    """使用 LangGraph 工作流处理对话请求，返回与 ConversationAgent.process 同构的结果。"""
    llm_client = _get_llm_client(request.model_id)
    graph = create_conversation_workflow(workflow_tools=workflow_tools, llm_client=llm_client)

    messages = list((existing_state or {}).get("messages", []))
    messages.append({"role": "user", "content": user_content})

    initial_state = {
        "messages": messages,
        "enable_prompt_optimization": True,
        "intent": None,
        "generation_request": None,
        "current_tool": None,
        "tool_result": None,
        "loop_count": 0,
        "is_complete": False,
    }

    config = {"configurable": {"thread_id": f"req_{request_id}"}}
    final_state: dict = dict(initial_state)

    async for state in graph.astream(initial_state, config=config):
        if isinstance(state, dict) and on_progress:
            if state.get("intent") and not final_state.get("intent"):
                await on_progress(_GRAPH_NODE_PROGRESS["intent"])
            elif state.get("generation_request") and not final_state.get("generation_request"):
                await on_progress(_GRAPH_NODE_PROGRESS["direct_execute"])
            elif state.get("tool_result") and not final_state.get("tool_result"):
                await on_progress(_GRAPH_NODE_PROGRESS["execute_tool"])
        if isinstance(state, dict):
            final_state = state

    intent = final_state.get("intent")
    tool_result = final_state.get("tool_result") or {}

    tasks: list = []
    workflow_ready = False
    if isinstance(tool_result, dict):
        if tool_result.get("task_id"):
            tasks = [tool_result]
            workflow_ready = True
        elif tool_result.get("selection_required"):
            workflow_tools.pending_generation = tool_result

    if tasks:
        reply = "生成任务已提交，请查看下方进度。"
    elif isinstance(tool_result, dict) and tool_result.get("selection_required"):
        reply = "请在弹出的选择框中补全生成参数。"
    elif intent in ("txt2img", "txt2video"):
        reply = "好的，正在处理你的生成请求。"
    else:
        reply = "我是 AI 绘画助手，描述你想生成的图片或视频，我来帮你实现！"

    if on_delta:
        await on_delta(reply)

    return {
        "reply": reply,
        "state": {"intent": intent},
        "workflow_ready": workflow_ready,
        "tasks": tasks,
        "context_usage": None,
    }


class ChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    message: str
    model_id: int
    session_id: Optional[int] = None
    generation_options: Optional[Dict[str, Any]] = None
    asset_ids: List[int] = Field(default_factory=list, max_length=10)


class ChatResponse(BaseModel):
    reply: str
    session_id: int
    user_conversation_id: Optional[int] = None
    agent_conversation_id: Optional[int] = None
    intent: Optional[str] = None
    workflow_ready: bool
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    generation_request: Optional[Dict[str, Any]] = None
    context_usage: Optional[Dict[str, Any]] = None


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """接口入口。聊天业务看 _process_chat，流式发送看 _stream_chat_events。"""
    return StreamingResponse(
        _stream_chat_events(request, current_user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_chat_events(request: ChatRequest, current_user: dict):
    """一边处理聊天，一边向前端发送进度和文字；最后发送 done 或 error。"""
    event_queue = asyncio.Queue()

    async def report_progress(message: str):
        await event_queue.put(("progress", {"message": message}))

    async def report_delta(text: str):
        await event_queue.put(("delta", {"text": text}))

    async def report_event(event: str, data: dict):
        await event_queue.put((event, data))

    # 创建任务只是安排执行；当前协程让出执行权后，聊天业务才有机会运行。
    chat_task = asyncio.create_task(
        _process_chat(request, current_user, report_progress, report_delta, report_event)
    )
    try:
        yield _encode_sse("progress", {"message": "正在准备对话上下文"})

        # 聊天结束后仍要发完队列中的文字，再发送最终结果。
        while not chat_task.done() or not event_queue.empty():
            event = await _wait_for_chat_event(event_queue, chat_task)
            if event is not None:
                event_name, data = event
                yield _encode_sse(event_name, data)
            elif not chat_task.done():
                yield ": keep-alive\n\n"

        result = chat_task.result()
        yield _encode_sse("done", result.model_dump())
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.exception("工作流对话流式请求失败 session_id=%s", request.session_id or "new")
        detail = getattr(error, "detail", None) or str(error) or "对话请求失败"
        if "overloaded" in str(detail).lower():
            detail = "上游对话模型服务当前过载，请稍后重试。"
        yield _encode_sse("error", {"message": detail})
    finally:
        # 浏览器断开或停止读取时，回收本次聊天任务。
        if not chat_task.done():
            chat_task.cancel()
        await asyncio.gather(chat_task, return_exceptions=True)


async def _wait_for_chat_event(event_queue: asyncio.Queue, chat_task: asyncio.Task):
    """等待下一条消息或聊天结束；15 秒无消息则返回 None，让发送方发心跳。"""
    # 获得消息是不是为空？
    if not event_queue.empty():
        return event_queue.get_nowait()
    # 如果消息空的话就再创建一个task去获取队列，等待下一条消息
    next_event_task = asyncio.create_task(event_queue.get())
    #然后同时等待
    try:
        completed, _ = await asyncio.wait(
            (chat_task, next_event_task),
            timeout=15,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if next_event_task in completed:
            return next_event_task.result()
        return None
    finally:
        # 超时、聊天完成或连接取消后，不留下仍在等待队列的任务。
        if not next_event_task.done():
            next_event_task.cancel()
        await asyncio.gather(next_event_task, return_exceptions=True)


def _encode_sse(event: str, data: dict) -> str:
    """把事件编码为前端约定的 SSE 文本；只拼字符串，不需要协程。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _process_chat(request: ChatRequest, current_user: dict, on_progress=None, on_delta=None, on_event=None) -> ChatResponse:
    """聊天主流程：读取会话 → 调用助手和工具 → 保存对话 → 返回结果。"""
    request_id = str(uuid.uuid4())[:8]
    user_id = current_user["id"]
    session_id = request.session_id or None
    started_at = time.perf_counter()
    logger.info(
        "工作流对话开始 request_id=%s user_id=%s session_id=%s message_length=%d",
        request_id, user_id, session_id or "new", len(request.message),
    )

    # 1. 读取历史，并确认会话属于当前用户。新会话返回 None。
    existing_state = await asyncio.to_thread(_load_chat_state, session_id, user_id)
    assets = await asyncio.to_thread(load_chat_assets, request.asset_ids, user_id) if request.asset_ids else []
    user_content = await asyncio.to_thread(build_asset_content, request.message, assets)

    # 2. 新会话延迟到工具真正提交任务，或聊天成功后再创建。
    def ensure_session():
        nonlocal session_id
        if session_id is None:
            session_id = WorkflowRepository.create_session(user_id)
        return session_id

    user_conversation_id = None

    def ensure_conversation():
        nonlocal user_conversation_id
        if user_conversation_id is None:
            user_conversation_id = WorkflowRepository.add_conversation(
                ensure_session(), "user", request.message, asset_ids=request.asset_ids
            )
        return user_conversation_id

    generation_options = request.generation_options or {}
    workflow_tools = WorkflowTools(current_user, ensure_session, generation_options, ensure_conversation)
    workflow_tools.asset_ids = [asset["id"] for asset in assets]
    for previous_message in (existing_state or {}).get("messages", []):
        workflow_tools.allowed_asset_ids.update(previous_message.get("asset_ids", []))
    workflow_tools.allowed_asset_ids.update(workflow_tools.asset_ids)
    previous_tasks = session_tasks(session_id, user_id) if session_id else []
    events = []

    async def record_event(event: str, data: dict):
        if event == "trace":
            events.append(data)
        if on_event:
            await on_event(event, data)

    # 3. 助手理解需求；发现工具时调用 discover，执行工具时调用 discover_and_execute。
    if generation_options:
        pending = (existing_state or {}).get("generation_request")
        if not pending or pending["media_type"] != generation_options.get("media_type"):
            raise HTTPException(status_code=400, detail="生成请求已变化，请重新发起生成并确认参数")
        if pending.get("input_asset_ids"):
            workflow_tools.allowed_asset_ids.update(pending["input_asset_ids"])
            tool_name = pending.get("tool_name") or ("txt2img" if pending["media_type"] == "image" else "txt2video")
            task = await workflow_tools.discover_and_execute(tool_name, {
                "prompt": pending["prompt"], "input_asset_ids": pending["input_asset_ids"]
            })
            if task.get("task_id"):
                reply = "生成任务已提交，请查看下方进度。"
                result = {"reply": reply, "state": {"intent": "batch_image" if tool_name in ("txt2img", "img2img") else "text_to_video"}, "tasks": [task], "workflow_ready": True}
            else:
                result = {"reply": "请在弹出的选择框中补全生成参数。", "state": existing_state, "tasks": [], "workflow_ready": False}
        else:
            agent = get_conversation_agent(request.model_id)
            result = await agent.process(
                message=request.message,
                session_id=session_id,
                user_id=user_id,
                existing_state=existing_state,
                on_progress=on_progress,
                on_delta=on_delta,
                tool_executor=workflow_tools.discover_and_execute,
                tool_discoverer=workflow_tools.discover,
                executions=previous_tasks,
                request_id=request_id,
                user_content=user_content,
                on_event=record_event,
            )
        if on_delta and result.get("tasks"):
            await on_delta(result["reply"])
    else:
        result = await _run_conversation_graph(
            request=request,
            workflow_tools=workflow_tools,
            existing_state=existing_state,
            user_content=user_content,
            request_id=request_id,
            on_progress=on_progress,
            on_delta=on_delta,
        )

    # 4. 保存本轮对话和会话状态。
    session_id = ensure_session()
    pending_generation = workflow_tools.pending_generation if isinstance(workflow_tools.pending_generation, dict) else None
    if pending_generation:
        result["state"]["intent"] = "batch_image" if pending_generation["media_type"] == "image" else "text_to_video"
    result["metadata"] = {"events": events, "context_usage": result.get("context_usage")}
    if request.asset_ids:
        ensure_conversation()
    user_conversation_id, agent_conversation_id = _save_chat_result(
        session_id, request.message, result, previous_tasks, user_conversation_id
    )
    # 会话字段只保存尚未执行的选择请求；执行参数的唯一来源是执行记录。
    if pending_generation:
        WorkflowRepository.update_session(session_id, parameters={"generation_request": pending_generation})
    elif result.get("tasks"):
        WorkflowRepository.update_session(session_id, parameters={})
    logger.info(
        "工作流对话完成 request_id=%s session_id=%s intent=%s workflow_ready=%s elapsed_ms=%d",
        request_id, session_id, result["state"].get("intent"),
        result.get("workflow_ready", False), round((time.perf_counter() - started_at) * 1000),
    )
    return ChatResponse(
        reply=result["reply"],
        session_id=session_id,
        user_conversation_id=user_conversation_id,
        agent_conversation_id=agent_conversation_id,
        intent=result["state"].get("intent"),
        workflow_ready=result.get("workflow_ready", False),
        tasks=session_tasks(session_id, user_id),
        generation_request=pending_generation,
        context_usage=result.get("context_usage"),
    )


def _load_chat_state(session_id: Optional[int], user_id: int) -> Optional[ConversationState]:
    """恢复已有会话的权限、历史消息和参数；新会话暂不写数据库。"""
    if not session_id:
        return None

    session = WorkflowRepository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="无权访问此会话")

    conversations = WorkflowRepository.get_conversations(session_id)
    return {
        "session_id": session_id,
        "user_id": user_id,
        "messages": [
            {"role": item["role"], "content": build_asset_content(item["message"], load_chat_assets(item["asset_ids"], user_id))
             if item.get("asset_ids") else item["message"], "asset_ids": item.get("asset_ids", [])}
            for item in conversations
        ],
        "intent": session.get("intent"),
        "generation_request": session.get("parameters", {}).get("generation_request"),
        "missing_params": [],
        "workflow_ready": session["status"] == "ready",
        "current_step": "parameter_extraction" if session.get("intent") else "intent_recognition",
    }


def _save_chat_result(
    session_id: int, message: str, result: dict, previous_tasks: list,
    user_conversation_id: Optional[int] = None,
):
    """保存用户和助手消息；根据本轮提交情况更新会话状态。"""
    if user_conversation_id is None:
        user_conversation_id = WorkflowRepository.add_conversation(session_id, "user", message)
    agent_conversation_id = WorkflowRepository.add_conversation(
        session_id, "agent", result["reply"], metadata=result.get("metadata")
    )

    state = result["state"]
    if result.get("tasks"):
        WorkflowRepository.update_session(
            session_id,
            intent=state.get("intent"),
            status="executing",
        )
    elif state.get("intent") and not previous_tasks:
        WorkflowRepository.update_session(
            session_id,
            intent=state["intent"],
            status="collecting",
        )

    return user_conversation_id, agent_conversation_id


class SessionResponse(BaseModel):
    id: int
    intent: Optional[str]
    status: str
    created_at: str
    updated_at: str


@router.get("/sessions", response_model=List[SessionResponse])
async def get_sessions(current_user: dict = Depends(get_current_user)):
    """获取用户的会话列表"""
    user_id = current_user["id"]
    sessions = WorkflowRepository.get_user_sessions(user_id, limit=20)

    return [
        SessionResponse(
            id=s["id"],
            intent=s["intent"],
            status=s["status"],
            created_at=s["created_at"].isoformat(),
            updated_at=s["updated_at"].isoformat()
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: int, current_user: dict = Depends(get_current_user)):
    """软删除当前用户的会话。"""
    user_id = current_user["id"]
    session = WorkflowRepository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="无权访问此会话")
    WorkflowRepository.soft_delete_session(session_id, user_id)


class SessionDetailResponse(BaseModel):
    id: int
    intent: Optional[str]
    generation_request: Optional[Dict[str, Any]] = None
    status: str
    conversations: List[Dict[str, Any]]
    tasks: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(session_id: int, current_user: dict = Depends(get_current_user)):
    """获取会话详情"""
    user_id = current_user["id"]

    session = WorkflowRepository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="无权访问此会话")

    conversations = WorkflowRepository.get_conversations(session_id)

    return SessionDetailResponse(
        id=session["id"],
        intent=session.get("intent"),
        generation_request=session.get("parameters", {}).get("generation_request"),
        status=session["status"],
        tasks=session_tasks(session_id, user_id),
        conversations=[
            {
                "id": conv["id"],
                "role": conv["role"],
                "message": conv["message"],
                "created_at": conv["created_at"].isoformat(),
                "assets": asset_previews(load_chat_assets(conv["asset_ids"], user_id)) if conv.get("asset_ids") else [],
                "events": conv.get("metadata", {}).get("events", []),
                "context_usage": conv.get("metadata", {}).get("context_usage"),
            }
            for conv in conversations
        ]
    )
