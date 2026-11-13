"""
条件路由函数
"""
from typing import Dict, Any
from langgraph.graph import END
import logging

logger = logging.getLogger(__name__)


def should_optimize_prompt(state: Dict[str, Any]) -> str:
    """
    决定是否走提示词优化子图

    决策树:
    1. 用户未启用优化 → direct_execute
    2. 意图不是生成类 → direct_execute
    3. 否则 → prompt_enhance

    Returns:
        "direct_execute" 或 "prompt_enhance"
    """
    if not state.get("enable_prompt_optimization", False):
        logger.info("提示词优化未启用，走 direct_execute")
        return "direct_execute"

    intent = state.get("intent")
    if intent not in ["txt2img", "txt2video"]:
        logger.info(f"意图 {intent} 不是生成类，走 direct_execute")
        return "direct_execute"

    logger.info("启用提示词优化，走 prompt_enhance")
    return "prompt_enhance"


def should_continue(state: Dict[str, Any]) -> str:
    """
    检查是否结束或继续循环

    终止条件:
    1. is_complete=True
    2. loop_count >= 8
    3. tool_result 中有 selection_required (需要用户交互)

    Returns:
        END 或 "intent"
    """
    if state.get("is_complete", False):
        logger.info("任务已完成，结束图执行")
        return END

    if state.get("loop_count", 0) >= 8:
        logger.warning("达到最大循环次数，强制结束")
        return END

    tool_result = state.get("tool_result") or {}
    if isinstance(tool_result, dict) and tool_result.get("selection_required"):
        logger.info("需要用户选择参数，暂停执行")
        return END

    logger.info("继续循环，回到 intent 节点")
    return "intent"
