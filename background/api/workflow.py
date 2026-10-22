"""
工作流 API
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os

from api.auth import get_current_user
from agents.conversation_agent import ConversationAgent
from repositories.workflow_repo import WorkflowRepository
from repositories.generation_repo import get_language_model_info
from config import get_provider_config_by_rfid
from graph.states import ConversationState

router = APIRouter(prefix="/workflow", tags=["workflow"])

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
    """对话接口"""
    user_id = current_user["id"]
    session_id = request.session_id

    # 获取或创建会话
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
        # 创建新会话
        session_id = WorkflowRepository.create_session(user_id)
        existing_state = None

    # 处理消息
    agent = get_conversation_agent()
    result = await agent.process(
        message=request.message,
        session_id=session_id,
        user_id=user_id,
        existing_state=existing_state
    )

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
            parameters=result["state"]["parameters"]
        )

    return ChatResponse(
        reply=result["reply"],
        session_id=session_id,
        intent=result.get("intent"),
        parameters=result.get("parameters"),
        workflow_ready=result.get("workflow_ready", False)
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
