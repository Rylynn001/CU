"""
提示词优化子图 (Seedance)

流程: Analyze → Generate Instruction → LLM Enhance
"""
from typing import Dict, Any, Optional
import logging
from langgraph.graph import StateGraph, END

from ..states import PromptEnhanceState
from ...services.seedance_tool import SeedancePromptTool

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 子图节点
# ─────────────────────────────────────────────

async def analyze_need_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    分析用户需求，判断 Seedance 版本和路径
    """
    user_prompt = state.get("user_prompt", "")

    logger.info(f"分析 Seedance 需求: {user_prompt[:100]}...")

    tool = SeedancePromptTool()

    version = tool.determine_version(user_prompt)
    path = tool.determine_path(user_prompt)

    logger.info(f"Seedance 版本: {version}, 路径: {path}")

    return {
        "seedance_version": version,
        "seedance_path": path
    }


async def generate_instruction_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    生成给 LLM 的优化指令
    """
    tool = SeedancePromptTool()

    instruction = tool.generate_prompt_instruction(
        user_request=state["user_prompt"],
        path=state.get("seedance_path", "A"),
        version=state.get("seedance_version", "2.5")
    )

    logger.info(f"生成优化指令，路径={state.get('seedance_path')}, 版本={state.get('seedance_version')}")

    return {"instruction": instruction}


async def llm_enhance_node(state: Dict[str, Any], llm_client=None, model_name: Optional[str] = None) -> Dict[str, Any]:
    """
    使用 LLM 优化提示词

    Args:
        state: PromptEnhanceState
        llm_client: 外部注入的 LLM client (AsyncOpenAI)
    """
    if llm_client is None:
        logger.warning("LLM client 未注入，直接返回原始提示词")
        return {"enhanced_prompt": state["user_prompt"]}

    instruction = state.get("instruction", "")
    user_prompt = state.get("user_prompt", "")

    logger.info("调用 LLM 优化提示词...")

    try:
        response = await llm_client.chat.completions.create(
            model=model_name or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": instruction},
                {"role": "user", "content": user_prompt}
            ]
        )
        enhanced = response.choices[0].message.content
        if not isinstance(enhanced, str) or not enhanced.strip():
            raise ValueError("提示词优化未返回有效内容")
        logger.info("提示词优化完成")
        return {"enhanced_prompt": enhanced}

    except Exception as e:
        logger.error(f"LLM 优化失败，返回原始提示词: {e}")
        return {"enhanced_prompt": user_prompt}


# ─────────────────────────────────────────────
# 子图工厂
# ─────────────────────────────────────────────

def create_prompt_enhance_subgraph(llm_client=None, model_name: Optional[str] = None):
    """
    创建提示词优化子图

    Args:
        llm_client: 外部注入的 LLM client

    Returns:
        编译好的子图
    """
    subgraph = StateGraph(PromptEnhanceState)

    # 注入 llm_client
    async def _llm_enhance(state):
        return await llm_enhance_node(state, llm_client=llm_client, model_name=model_name)

    subgraph.add_node("analyze", analyze_need_node)
    subgraph.add_node("generate_ins", generate_instruction_node)
    subgraph.add_node("enhance", _llm_enhance)

    subgraph.set_entry_point("analyze")
    subgraph.add_edge("analyze", "generate_ins")
    subgraph.add_edge("generate_ins", "enhance")
    subgraph.add_edge("enhance", END)

    return subgraph.compile()
