"""
工具节点：准备工具参数和执行工具
"""
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


async def direct_execute_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    直接准备工具参数，不做提示词优化

    Args:
        state: ConversationState

    Returns:
        更新的状态，包含 current_tool 和 generation_request
    """
    intent = state.get("intent")
    messages = state.get("messages", [])

    if not messages:
        logger.warning("消息列表为空")
        return {"is_complete": True}

    # 获取最后一条用户消息内容
    last_msg = messages[-1]
    if hasattr(last_msg, "content"):
        last_message = last_msg.content
    else:
        last_message = last_msg.get("content", "")

    logger.info(f"Direct execute: intent={intent}")

    # 根据意图选择工具
    if intent == "txt2img":
        return {
            "current_tool": "txt2img",
            "generation_request": {"prompt": last_message}
        }
    elif intent == "txt2video":
        return {
            "current_tool": "txt2video",
            "generation_request": {"prompt": last_message}
        }
    else:
        # 普通对话，无需工具
        logger.info("普通对话，不需要工具执行")
        return {"is_complete": True}


async def execute_tool_node(
    state: Dict[str, Any],
    workflow_tools=None  # 外部注入的工具执行器
) -> Dict[str, Any]:
    """
    执行工具调用

    Args:
        state: ConversationState
        workflow_tools: WorkflowTools 实例

    Returns:
        更新的状态，包含 tool_result 和 is_complete
    """
    tool_name = state.get("current_tool")
    generation_request = state.get("generation_request")

    if not tool_name or not generation_request:
        logger.warning("工具名或参数为空，跳过执行")
        return {"is_complete": True}

    logger.info(f"执行工具: {tool_name}, 参数: {generation_request}")

    if workflow_tools is None:
        logger.error("WorkflowTools 未注入，无法执行工具")
        return {
            "tool_result": {"error": "工具执行器未初始化"},
            "is_complete": True
        }

    try:
        # 调用 WorkflowTools.discover_and_execute
        result = await workflow_tools.discover_and_execute(tool_name, generation_request)

        # 检查是否需要用户选择参数
        if result.get("selection_required"):
            logger.info("需要用户选择参数，暂停执行")
            return {
                "tool_result": result,
                "is_complete": False
            }

        logger.info(f"工具执行完成: {tool_name}")
        return {
            "tool_result": result,
            "is_complete": True
        }

    except Exception as e:
        logger.error(f"工具执行失败: {e}", exc_info=True)
        return {
            "tool_result": {"error": str(e)},
            "is_complete": True
        }
