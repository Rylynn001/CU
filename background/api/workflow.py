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
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from api.auth import get_current_user
from agents.conversation_agent import ConversationAgent
from repositories.workflow_repo import WorkflowRepository
from repositories.generation_repo import get_language_model_info
from config import get_provider_config_by_rfid
from graph.states import ConversationState

router = APIRouter(prefix="/workflow", tags=["workflow"])
logger = logging.getLogger(__name__)

# 延迟初始化对话 Agent（避免启动时因缺少环境变量而失败）
conversation_agent = None


def get_conversation_agent() -> ConversationAgent:
    """获取或初始化对话 Agent（从数据库获取配置）"""
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


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """兼容旧调用方的非流式对话接口。"""
    return await _process_chat(request, current_user)


async def _process_chat(request: ChatRequest, current_user: dict, on_progress=None) -> ChatResponse:
    request_id = str(uuid.uuid4())[:8]
    user_id = current_user["id"]
    session_id = request.session_id
    started_at = time.perf_counter()
    logger.info(
        "工作流对话开始 request_id=%s user_id=%s session_id=%s message_length=%d",
        request_id, user_id, session_id or "new", len(request.message)
    )

    # 获取或创建会话
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

    # 处理消息（先处理，成功后再创建会话）
    agent = get_conversation_agent()
    result = await agent.process(
        message=request.message,
        session_id=session_id,
        user_id=user_id,
        existing_state=existing_state,
        on_progress=on_progress
    )

    # agent 处理成功后，如果是新会话，现在才创建
    if is_new_session:
        session_id = WorkflowRepository.create_session(user_id)

    # 保存对话记录
    WorkflowRepository.add_conversation(session_id, "user", request.message)
    WorkflowRepository.add_conversation(session_id, "agent", result["reply"])

    # 更新会话状态
    if result.get("workflow_ready"):
        WorkflowRepository.update_session(
            session_id,
            intent=result["intent"],
            parameters=result["parameters"],
            status="ready"
        )
    elif result["state"].get("intent"):
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
        workflow_ready=result.get("workflow_ready", False)
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """以 SSE 发送处理阶段、逐段回复和最终会话状态。"""
    async def events():
        queue = asyncio.Queue()

        async def report_progress(stage: str):
            await queue.put(("progress", {"message": stage}))

        async def send(event: str, data: dict):
            payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            return payload

        task = asyncio.create_task(_process_chat(request, current_user, report_progress))
        try:
            yield await send("progress", {"message": "正在准备对话上下文"})
            while not task.done() or not queue.empty():
                if not queue.empty():
                    event, data = queue.get_nowait()
                    yield await send(event, data)
                    continue
                queue_task = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    (task, queue_task), timeout=15, return_when=asyncio.FIRST_COMPLETED
                )
                if queue_task in done:
                    event, data = queue_task.result()
                    yield await send(event, data)
                else:
                    queue_task.cancel()
                    if not task.done():
                        yield ": keep-alive\n\n"
            result = task.result()
            for offset in range(0, len(result.reply), 12):
                yield await send("delta", {"text": result.reply[offset:offset + 12]})
            yield await send("done", result.model_dump())
        except asyncio.CancelledError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise
        except Exception as error:
            logger.exception("工作流对话流式请求失败 session_id=%s", request.session_id or "new")
            yield await send("error", {"message": str(error) or "对话请求失败"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
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
        conversations=[
            {
                "role": conv["role"],
                "message": conv["message"],
                "created_at": conv["created_at"].isoformat()
            }
            for conv in conversations
        ]
    )
