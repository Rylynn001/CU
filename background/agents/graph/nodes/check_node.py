"""
完成检查节点
"""
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def check_done_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    检查是否完成，防止无限循环

    Args:
        state: ConversationState

    Returns:
        更新的状态，包含 loop_count 和 is_complete
    """
    loop_count = state.get("loop_count", 0) + 1

    logger.info(f"检查完成状态，当前循环次数: {loop_count}")

    # 防止无限循环
    if loop_count >= 8:
        logger.warning(f"达到最大循环次数 {loop_count}，强制结束")
        return {"is_complete": True, "loop_count": loop_count}

    return {"loop_count": loop_count}
