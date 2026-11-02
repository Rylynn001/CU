"""
LangGraph 状态定义
"""
from typing import TypedDict, Optional, List, Any, Dict


class ConversationState(TypedDict):
    """对话状态"""
    session_id: Optional[int]
    user_id: int
    messages: List[Dict[str, str]]  # [{"role": "user/agent", "content": "..."}]
    intent: Optional[str]  # short_drama, batch_image, single_video, etc.
    parameters: Dict[str, Any]  # 已提取的参数
    missing_params: List[str]  # 还需要询问的参数
    workflow_ready: bool  # 参数是否完整
    current_step: str  # intent_recognition, parameter_extraction, asking, validation, ready


class TaskState(TypedDict):
    """工作流执行状态"""
    workflow_id: str
    session_id: int
    user_id: int

    # 任务信息
    intent: str
    parameters: Dict[str, Any]

    # 执行状态
    status: str  # running, paused, completed, failed
    current_node: str
    progress: float  # 0.0 - 1.0

    # 审核相关
    pending_review_id: Optional[str]
    review_result: Optional[Dict[str, Any]]

    # 任务结果
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    retry_count: int

    # 中间数据
    script_content: Optional[str]
    characters: Optional[List[Dict[str, Any]]]
    shots: Optional[List[Dict[str, Any]]]
    images: Optional[List[Dict[str, Any]]]
    videos: Optional[List[Dict[str, Any]]]

    # 元数据
    metadata: Dict[str, Any]
