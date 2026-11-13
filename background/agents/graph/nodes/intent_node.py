"""
意图识别节点
"""
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


async def intent_recognition_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    识别用户意图

    Args:
        state: ConversationState

    Returns:
        更新的状态，包含 intent 字段
    """
    messages = state.get("messages", [])
    if not messages:
        logger.warning("消息列表为空，无法识别意图")
        return {"intent": "chat", "is_complete": True}

    # 获取最后一条用户消息内容，兼容 dict 和 HumanMessage/BaseMessage 两种格式
    last_msg = messages[-1]
    if hasattr(last_msg, "content"):
        last_message = last_msg.content  # LangChain BaseMessage 对象
    else:
        last_message = last_msg.get("content", "")  # 普通 dict

    logger.info(f"识别意图，用户消息: {last_message[:100]}...")

    # 关键词检测
    txt2img_keywords = ["图片", "生成图", "画一张", "图像", "image", "画", "图"]
    txt2video_keywords = ["视频", "seedance", "即梦", "video", "动画", "短片"]

    intent = "chat"  # 默认

    if any(kw in last_message for kw in txt2video_keywords):
        intent = "txt2video"
    elif any(kw in last_message for kw in txt2img_keywords):
        intent = "txt2img"

    logger.info(f"识别结果: intent={intent}")

    return {"intent": intent}
