"""
LangGraph 状态定义
"""
from typing import TypedDict, Optional, List, Any, Dict, Annotated
from langgraph.graph.message import add_messages


class ConversationState(TypedDict):
    """对话状态（主图）"""
    session_id: Optional[int]
    user_id: int
    messages: Annotated[List[Dict[str, str]], add_messages]  # LangGraph 消息管理
    intent: Optional[str]  # txt2img, txt2video, chat
    generation_request: Optional[Dict[str, Any]]  # 生成请求参数
    generation_draft: Optional[Dict[str, Any]]  # 尚未完成提示词处理的计划草稿，等待用户补充或重试
    asset_ids: List[int]  # 本轮新补充的真实素材编号，只用于恢复暂停的步骤
    enable_prompt_optimization: bool  # 是否启用提示词优化
    current_tool: Optional[str]  # 当前执行的工具
    tool_result: Optional[Dict]  # 工具执行结果
    loop_count: int  # 循环计数(防止无限循环)
    is_complete: bool  # 是否完成
    workflow_ready: bool  # 参数是否完整(兼容旧代码)
    current_step: str  # 当前步骤(兼容旧代码)


class PromptEnhanceState(TypedDict):
    """提示词优化子图状态"""
    user_prompt: str  # 原始提示词
    messages: List[Any]  # 完整对话，保留技能追问和用户确认
    intent: str  # txt2img/txt2video
    enhanced_prompt: Optional[str]  # 增强后的提示词
    clarification: Optional[Dict[str, Any]]  # 真正缺少创作内容/参考素材时的结构化追问
    error: Optional[str]  # 优化失败时中止生成
    seedance_version: Optional[str]  # Seedance 版本(2.0/2.5)
    seedance_path: Optional[str]  # Seedance 路径(A/B/C/D)
    instruction: Optional[str]  # 生成的指令(中间结果)


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
