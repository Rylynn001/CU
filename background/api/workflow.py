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
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from api.auth import get_current_user
from agents.conversation_agent import ConversationAgent
from repositories.workflow_repo import WorkflowRepository
from repositories.generation_repo import get_language_model_info
from config import get_provider_config_by_rfid
from graph.states import ConversationState
from services.workflow_image_tools import WorkflowImageTools, session_tasks

router = APIRouter(prefix="/workflow", tags=["workflow"])
logger = logging.getLogger(__name__)

# 延迟初始化对话 Agent（避免启动时因缺少环境变量而失败）
conversation_agent = None


def get_conversation_agent() -> ConversationAgent:
    """获取或初始化对话 Agent（从数据库获取配置）。

    这里配置的是负责理解对话、选择工具的“语言模型”，不是用户要用来出图的图片模型。
    """
    global conversation_agent
    if conversation_agent is None:
        # 从数据库获取 language 类型的 openai 模型
        model_info = get_language_model_info(provider='openai')
        if not model_info:
            raise HTTPException(
                status_code=500,
                detail="未找到可用的语言模型配置（type=language, provider=openai）"
            )

        # 获取 provider 配置（解密后的 api_key 和 base_url）
        provider_config = get_provider_config_by_rfid(model_info['rfid'])
        if not provider_config:
            raise HTTPException(
                status_code=500,
                detail=f"未找到模型 {model_info['name']} 的 provider 配置"
            )

        conversation_agent = ConversationAgent(
            api_key=provider_config['api_key'],
            base_url=provider_config['base_url'],
            model=model_info['name']
        )
    return conversation_agent


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    intent: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    workflow_ready: bool
    tasks: List[Dict[str, Any]] = Field(default_factory=list)


async def _process_chat(request: ChatRequest, current_user: dict, on_progress=None, on_delta=None) -> ChatResponse:
    """处理一条聊天消息：恢复上下文、调用 Agent、保存对话并返回结果。"""
    request_id = str(uuid.uuid4())[:8]
    user_id = current_user["id"]
    session_id = request.session_id
    started_at = time.perf_counter()
    logger.info(
        "工作流对话开始 request_id=%s user_id=%s session_id=%s message_length=%d",
        request_id, user_id, session_id or "new", len(request.message)
    )

    # 第一步：恢复会话上下文。已有会话必须属于当前用户；随后读取此前的 user/agent 消息，
    # 这些历史会被传给 ConversationAgent，避免每一轮都像第一次聊天。
    is_new_session = False
    if session_id:
        session_data = WorkflowRepository.get_session(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")
        if session_data["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="无权访问此会话")

        # 加载对话历史
        conversations = WorkflowRepository.get_conversations(session_id)
        messages = [{"role": conv["role"], "content": conv["message"]} for conv in conversations]

        existing_state: ConversationState = {
            "session_id": session_id,
            "user_id": user_id,
            "messages": messages,
            "intent": session_data.get("intent"),
            "parameters": session_data.get("parameters", {}),
            "missing_params": [],
            "workflow_ready": session_data["status"] == "ready",
            "current_step": "parameter_extraction" if session_data.get("intent") else "intent_recognition"
        }
    else:
        # 新会话：先不创建，等 agent 处理成功后再创建
        is_new_session = True
        session_id = None
        existing_state = None

    # 图片工具需要 session_id 才能把执行记录关联到聊天会话。
    # 如果是新会话，等真正要执行工具时再创建；普通闲聊则在 Agent 返回后创建。
    def ensure_session():
        nonlocal session_id, is_new_session
        if is_new_session:
            session_id = WorkflowRepository.create_session(user_id)
            is_new_session = False
        return session_id

    # 第二步：创建 Agent 和工具执行器。image_tools.execute 会被作为回调传入 Agent；
    # 模型一旦返回工具调用，ConversationAgent 就通过这个回调实际查询数据库或提交生图任务。
    agent = get_conversation_agent()
    image_tools = WorkflowImageTools(current_user, ensure_session)
    executions = session_tasks(session_id, user_id) if session_id else []
    # =====【进入 Agent 的位置】=====
    # agent.process 内部才会请求语言模型。这里传入的 on_delta/on_progress
    # 用于把模型文字和执行阶段转成 SSE 事件；executions 用于让模型知道会话已有任务。
    result = await agent.process(
        message=request.message,
        session_id=session_id,
        user_id=user_id,
        existing_state=existing_state,
        on_progress=on_progress,
        on_delta=on_delta,
        tool_executor=image_tools.discover_and_execute,
        tool_discoverer=image_tools.discover,
        executions=executions,
        request_id=request_id,
    )

    # 仅对话且没有触发工具时，在处理完成后创建会话。
    if is_new_session:
        ensure_session()

    # 第三步：Agent 已返回后，把本轮用户消息和 Agent 的最终文字保存到会话历史。
    WorkflowRepository.add_conversation(session_id, "user", request.message)
    WorkflowRepository.add_conversation(session_id, "agent", result["reply"])

    # 更新会话状态
    if result.get("tasks"):
        WorkflowRepository.update_session(
            session_id,
            intent=result["state"].get("intent"),
            parameters=result["state"].get("parameters", {}),
            status="executing"
        )
    elif result["state"].get("intent") and not executions:
        WorkflowRepository.update_session(
            session_id,
            intent=result["state"]["intent"],
            parameters=result["state"]["parameters"],
            status="collecting"
        )

    logger.info(
        "工作流对话完成 request_id=%s session_id=%s intent=%s workflow_ready=%s elapsed_ms=%d",
        request_id, session_id, result["state"].get("intent"),
        result.get("workflow_ready", False), round((time.perf_counter() - started_at) * 1000)
    )
    return ChatResponse(
        reply=result["reply"],
        session_id=session_id,
        intent=result["state"].get("intent"),
        parameters=result["state"].get("parameters"),
        workflow_ready=result.get("workflow_ready", False),
        tasks=session_tasks(session_id, user_id),
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """聊天流式接口：把 Agent 的进度、文字和最终结果通过 SSE 发给浏览器。"""
    async def events():
        # 创建一个异步队列，作为“业务处理”和“向浏览器发送数据”之间的传递通道。
        # _process_chat 运行时会把进度/文字放进队列；下面的循环负责取出并发送。
        queue = asyncio.Queue()

        # 定义进度回调：Agent 或工具调用它时，把一个 progress 事件放进队列。
        async def report_progress(stage: str):
            # stage 是人能读懂的状态，例如“正在查询数据库中的图片模型”。
            await queue.put(("progress", {"message": stage}))

        # 定义文字回调：语言模型每返回一段可展示文字，Agent 就会调用这个函数。
        async def report_delta(text: str):
            # delta 代表增量文本；前端收到后会把 text 追加到当前助手消息里。
            await queue.put(("delta", {"text": text}))

        # 定义 SSE 编码函数：把事件名称和数据字典转换成浏览器能识别的文本格式。
        async def send(event: str, data: dict):
            # SSE 每个事件由 event 行、data 行和空行组成；空行表示这个事件结束。
            # ensure_ascii=False 保留中文，不把中文转成类似 \\u4e2d 的编码。
            payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            # 返回已经编码好的事件文本，外层通过 yield 立即交给 HTTP 响应。
            return payload

        # 启动真正的聊天处理，但不在这里等待它全部完成。
        # create_task 让 _process_chat 在后台继续运行，当前协程可以同时向浏览器发事件。
        task = asyncio.create_task(_process_chat(request, current_user, report_progress, report_delta))
        try:
            # 先告诉前端请求已开始，避免模型还没响应时页面看起来毫无反应。
            yield await send("progress", {"message": "正在准备对话上下文"})
            # 只要业务 task 尚未结束，或队列里还留有未发送事件，就继续循环。
            while not task.done() or not queue.empty():
                # 如果队列已有事件，不等待，马上取出。
                if not queue.empty():
                    # get_nowait 立即取队首事件；前面已检查非空，所以这里不会等待。
                    event, data = queue.get_nowait()
                    # yield 会把这一条 SSE 数据发送给浏览器。
                    yield await send(event, data)
                    # 一次循环发送一条事件，然后回到 while 检查剩余事件。
                    continue
                # 队列暂时为空时，创建一个等待“下一条事件”的异步任务。
                queue_task = asyncio.create_task(queue.get())
                # 同时等待两件事：业务处理结束，或队列收到新事件。
                # timeout=15 表示最多等 15 秒，防止连接长时间没有任何数据。
                done, _ = await asyncio.wait(
                    (task, queue_task), timeout=15, return_when=asyncio.FIRST_COMPLETED
                )
                # 如果队列先收到事件，就读取该事件并立刻发给浏览器。
                if queue_task in done:
                    # result() 取出 queue.get() 返回的 (事件名, 数据)。
                    event, data = queue_task.result()
                    # 将 progress 或 delta 事件编码为 SSE 并发送。
                    yield await send(event, data)
                else:
                    # 15 秒内没有事件时，取消正在等待队列的任务，避免留下无用后台任务。
                    queue_task.cancel()
                    # 如果 Agent 仍在处理，发送 SSE 注释作为心跳，维持代理/浏览器连接。
                    if not task.done():
                        yield ": keep-alive\n\n"
            # 循环结束表示 Agent 已完成，且进度/文字队列也已经清空。
            # Agent 和工具都处理完后，发送最终 done 事件，其中包括 session_id 和任务列表。
            # task.result() 取回 _process_chat 的最终 ChatResponse；若业务出错，这里会抛出异常。
            result = task.result()
            # Pydantic model_dump 把响应对象转换成字典，再作为 done 事件发给前端。
            yield await send("done", result.model_dump())
        except asyncio.CancelledError:
            # 浏览器断开连接或请求被取消时，也取消正在运行的业务处理任务。
            task.cancel()
            try:
                # 等待被取消的 task 真正结束，避免留下后台任务。
                await task
            except asyncio.CancelledError:
                # 预期中的取消异常在这里消化；外层仍需知道原请求已取消。
                pass
            # 重新抛出取消异常，让框架按取消请求处理。
            raise
        except Exception as error:
            # 记录完整异常堆栈，便于在后端日志中定位模型或工具错误。
            logger.exception("工作流对话流式请求失败 session_id=%s", request.session_id or "new")
            # 把错误转换成 SSE error 事件，让前端显示可读错误，而不是只看到连接断开。
            yield await send("error", {"message": str(error) or "对话请求失败"})

    # StreamingResponse 会在浏览器读取响应时逐次运行 events() 并发送其中 yield 的内容。
    return StreamingResponse(
        # events 是上面定义的异步生成器，负责持续产生 SSE 事件。
        events(),
        # 告诉浏览器响应内容是 Server-Sent Events，而不是普通 JSON。
        media_type="text/event-stream",
        # 这两个响应头禁止缓存，并提示 Nginx 等代理不要缓冲流式内容。
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


class SessionResponse(BaseModel):
    id: str
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


class SessionDetailResponse(BaseModel):
    id: str
    intent: Optional[str]
    parameters: Optional[Dict[str, Any]]
    status: str
    conversations: List[Dict[str, Any]]
    tasks: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(session_id: str, current_user: dict = Depends(get_current_user)):
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
        parameters=session.get("parameters"),
        status=session["status"],
        tasks=session_tasks(session_id, user_id),
        conversations=[
            {
                "role": conv["role"],
                "message": conv["message"],
                "created_at": conv["created_at"].isoformat()
            }
            for conv in conversations
        ]
    )
