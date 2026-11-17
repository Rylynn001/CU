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
from agents.graph.workflow import create_conversation_workflow
from openai import AsyncOpenAI
from repositories.workflow_repo import WorkflowRepository
from repositories import canvas_repo
from repositories.generation_repo import get_language_model_info
from config import get_provider_config_by_rfid
from agents.graph.states import ConversationState
from agents.services.workflow_tools import WorkflowTools, session_tasks
from agents.services.chat_assets import load_chat_assets, build_asset_content, asset_previews

router = APIRouter(prefix="/workflow", tags=["workflow"])
logger = logging.getLogger(__name__)


def _get_llm_client(model_id: int):
    """按模型编号创建 AsyncOpenAI 客户端，返回 (client, model_name)。"""
    model_info = get_language_model_info(model_id)
    if not model_info:
        raise HTTPException(status_code=404, detail=f"未找到语言模型配置（id={model_id}）")
    provider_config = get_provider_config_by_rfid(model_info['rfid'])
    if not provider_config:
        raise HTTPException(status_code=500, detail="未找到语言模型的服务配置")
    client = AsyncOpenAI(api_key=provider_config['api_key'], base_url=provider_config['base_url'])
    return client, model_info['name']


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
    user_content: str | list,
    request_id: str,
    on_progress=None,
    on_delta=None,
    on_event=None,
) -> dict:
    """使用 LangGraph 工作流处理对话请求，返回与 ConversationAgent.process 同构的结果。"""
    llm_client, model_name = _get_llm_client(request.model_id)
    graph = create_conversation_workflow(workflow_tools=workflow_tools, llm_client=llm_client, model_name=model_name, on_event=on_event)

    messages = list((existing_state or {}).get("messages", []))
    messages.append({"role": "user", "content": user_content})  # LangChain 标准角色

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

    async for state in graph.astream(initial_state, config=config, stream_mode="values"):
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

    logger.info("图执行结束 request_id=%s intent=%s result_keys=%s", request_id, intent, list(tool_result))

    tasks: list = []
    workflow_ready = False
    reply = None

    if isinstance(tool_result, dict):
        if tool_result.get("error"):
            raise HTTPException(status_code=502, detail=str(tool_result["error"]))
        if tool_result.get("reply"):
            # 对话结果
            reply = tool_result["reply"]
        elif tool_result.get("task_id"):
            tasks = [tool_result]
            workflow_ready = True
            reply = "生成任务已提交，请查看下方进度。"
        elif tool_result.get("selection_required"):
            workflow_tools.pending_generation = tool_result["selection_required"]
            reply = "请在弹出的选择框中补全生成参数。"

    if not isinstance(reply, str) or not reply.strip():
        raise HTTPException(status_code=502, detail="本次处理未返回有效结果，请重试")

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
    canvas_id: int = Field(gt=0)
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
        if isinstance(text, str) and text:
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
    _require_canvas(request.canvas_id, user_id)
    started_at = time.perf_counter()
    logger.info(
        "工作流对话开始 request_id=%s user_id=%s session_id=%s message_length=%d",
        request_id, user_id, session_id or "new", len(request.message),
    )

    # 1. 读取历史，并确认会话属于当前用户。新会话返回 None。
    existing_state = await asyncio.to_thread(_load_chat_state, session_id, user_id, request.canvas_id)
    assets = await asyncio.to_thread(load_chat_assets, request.asset_ids, user_id) if request.asset_ids else []
    user_content = await asyncio.to_thread(build_asset_content, request.message, assets)

    # 2. 新会话延迟到工具真正提交任务，或聊天成功后再创建。
    def ensure_session():
        nonlocal session_id
        if session_id is None:
            session_id = WorkflowRepository.create_session(user_id, request.canvas_id)
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
    workflow_tools = WorkflowTools(current_user, ensure_session, generation_options, ensure_conversation, canvas_id=request.canvas_id)
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

    async def canvas_changed():
        await record_event('canvas_changed', {'canvas_id': request.canvas_id})

    workflow_tools.on_canvas_change = canvas_changed

    # 3. 助手理解需求；发现工具时调用 discover，执行工具时调用 discover_and_execute。
    if generation_options:
        pending = (existing_state or {}).get("generation_request")
        if not pending or pending["media_type"] != generation_options.get("media_type"):
            raise HTTPException(status_code=400, detail="生成请求已变化，请重新发起生成并确认参数")
        input_asset_ids = pending.get("input_asset_ids", [])
        workflow_tools.allowed_asset_ids.update(input_asset_ids)
        tool_name = 'generation_plan' if pending['media_type'] == 'plan' else (pending.get("tool_name") or ("txt2img" if pending["media_type"] == "image" else "txt2video"))
        tool_input = {'steps': pending['steps']} if pending['media_type'] == 'plan' else {"prompt": pending["prompt"], "input_asset_ids": input_asset_ids}
        await record_event("trace", {"type": "tool_call", "round": 1,
            "call_id": "confirmed-generation", "name": tool_name, "input": tool_input})
        task = await workflow_tools.confirm_plan(pending) if tool_name == 'generation_plan' else await workflow_tools.discover_and_execute(tool_name, tool_input)
        await record_event("trace", {"type": "tool_result", "round": 1,
            "call_id": "confirmed-generation", "name": tool_name, "output": task})
        if task.get("error"):
            raise HTTPException(status_code=502, detail=str(task["error"]))
        if task.get('plan_id'):
            result = {'reply': '任务计划已提交，节点和连线已创建，关闭页面后后台仍会继续执行。',
                      'state': {'intent': 'generation_plan'}, 'tasks': task['tasks'], 'workflow_ready': True}
        elif task.get("task_id"):
            reply = "生成任务已提交，请查看下方进度。"
            result = {"reply": reply, "state": {"intent": "batch_image" if tool_name in ("txt2img", "img2img") else "text_to_video"}, "tasks": [task], "workflow_ready": True}
        elif task.get("selection_required"):
            workflow_tools.pending_generation = task["selection_required"]
            result = {"reply": "请在弹出的选择框中补全生成参数。", "state": existing_state, "tasks": [], "workflow_ready": False}
        else:
            raise HTTPException(status_code=502, detail="生成任务未提交，请重试")
        if on_delta:
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
            on_event=record_event,
        )

    # 4. 保存本轮对话和会话状态。
    session_id = ensure_session()
    pending_generation = workflow_tools.pending_generation if isinstance(workflow_tools.pending_generation, dict) else None
    if pending_generation:
        result["state"]["intent"] = {'image': 'batch_image', 'video': 'text_to_video', 'plan': 'generation_plan'}[pending_generation['media_type']]
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


def _require_canvas(canvas_id: int, user_id: int):
    if not canvas_repo.get_canvas(canvas_id, user_id):
        raise HTTPException(status_code=404, detail="画布不存在")


def _require_session(session_id: int, user_id: int, canvas_id: int):
    _require_canvas(canvas_id, user_id)
    session = WorkflowRepository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session["user_id"] != user_id or session.get('canvas_id') != canvas_id:
        raise HTTPException(status_code=403, detail="会话不属于当前画布")
    return session


def _load_chat_state(session_id: Optional[int], user_id: int, canvas_id: int) -> Optional[ConversationState]:
    """恢复已有会话的权限、历史消息和参数；新会话暂不写数据库。"""
    if not session_id:
        return None

    session = _require_session(session_id, user_id, canvas_id)

    conversations = WorkflowRepository.get_conversations(session_id)

    def _normalize_role(role: str) -> str:
        """将数据库角色映射到 LangChain 支持的消息类型"""
        role_map = {"agent": "assistant", "user": "user", "human": "user"}
        return role_map.get(role, "user")

    return {
        "session_id": session_id,
        "user_id": user_id,
        "messages": [
            {"role": _normalize_role(item["role"]), "content": build_asset_content(item["message"], load_chat_assets(item["asset_ids"], user_id))
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
    canvas_id: int
    title: Optional[str] = None
    intent: Optional[str]
    status: str
    created_at: str
    updated_at: str


@router.get("/sessions", response_model=List[SessionResponse])
async def get_sessions(canvas_id: int, current_user: dict = Depends(get_current_user)):
    """获取用户的会话列表"""
    user_id = current_user["id"]
    _require_canvas(canvas_id, user_id)
    sessions = WorkflowRepository.get_user_sessions(user_id, canvas_id)

    return [
        SessionResponse(
            id=s["id"],
            canvas_id=s['canvas_id'],
            title=s.get('title'),
            intent=s["intent"],
            status=s["status"],
            created_at=s["created_at"].isoformat(),
            updated_at=s["updated_at"].isoformat()
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: int, canvas_id: int, current_user: dict = Depends(get_current_user)):
    """软删除当前用户的会话。"""
    user_id = current_user["id"]
    _require_session(session_id, user_id, canvas_id)
    WorkflowRepository.soft_delete_session(session_id, user_id)


@router.post('/plans/{plan_id}/retry')
async def retry_generation_plan(plan_id: str, canvas_id: int, current_user: dict = Depends(get_current_user)):
    from agents.services.plan_scheduler import retry_plan
    _require_canvas(canvas_id, current_user['id'])
    await asyncio.to_thread(retry_plan, plan_id, current_user['id'], canvas_id)
    return {'status': 'running'}


class SessionDetailResponse(BaseModel):
    id: int
    canvas_id: int
    intent: Optional[str]
    generation_request: Optional[Dict[str, Any]] = None
    status: str
    conversations: List[Dict[str, Any]]
    tasks: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(session_id: int, canvas_id: int, current_user: dict = Depends(get_current_user)):
    """获取会话详情"""
    user_id = current_user["id"]

    session = _require_session(session_id, user_id, canvas_id)

    conversations = WorkflowRepository.get_conversations(session_id)

    return SessionDetailResponse(
        id=session["id"],
        canvas_id=canvas_id,
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
