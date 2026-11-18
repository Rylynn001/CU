"""
提示词优化子图 (Seedance)

流程: Analyze → Generate Instruction → LLM Enhance
"""
from typing import Dict, Any, Optional
import json
import logging
from langgraph.graph import StateGraph, END

from ..states import PromptEnhanceState
from ..utils.prompt_validation import PromptEnhancementResult
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


async def llm_enhance_node(state: Dict[str, Any], llm_client=None, model_name: Optional[str] = None, on_usage=None, on_retry=None) -> Dict[str, Any]:
    """
    使用 LLM 优化提示词

    Args:
        state: PromptEnhanceState
        llm_client: 外部注入的 LLM client (AsyncOpenAI)
    """
    if llm_client is None:
        return {"error": "提示词优化模型未初始化"}

    instruction = state.get("instruction", "")
    user_prompt = state.get("user_prompt", "")
    messages = [{"role": "system", "content": instruction}]
    for message in state.get("messages", []):
        if isinstance(message, dict):
            role, content = message.get("role", "user"), message.get("content", "")
        else:
            role = {'human': 'user', 'ai': 'assistant', 'system': 'system'}.get(message.type, message.type)
            content = message.content
        messages.append({"role": "assistant" if role == "agent" else role, "content": content})
    if len(messages) == 1:
        messages.append({"role": "user", "content": user_prompt})
    # 历史中可能包含其他生成要求；明确当前处理的原始描述，用户补充只用于完善它。
    messages.append({"role": "system", "content": '当前已确认的生成描述：\n' + user_prompt})
    messages.append({"role": "system", "content": (
        '根据完整对话执行以上提示词优化规则，只返回 JSON 对象。'
        '本节点只处理已经确认要实际生成的任务；是否生成已由前一意图节点决定。'
        '每次只优化当前步骤，不能把“请优化以下步骤”误解成用户只要提示词。'
        '模型、平台、版本、比例、分辨率、时长、质量和张数由后续参数面板确认；不得因此追问，也不得把这些问题写进提示词。'
        '仅当创作内容本身或必须使用的参考素材确实缺失、且无法合理生成时，才要求用户补充。'
        '只返回 JSON：可直接生成时为 {"status":"ready","prompt":"最终完整生成提示词"}；'
        '确需用户补充时为 {"status":"needs_clarification","clarification_type":"content|reference","reply":"具体问题"}。'
        'ready 只能有 prompt；needs_clarification 只能有 reply 和 clarification_type。'
        '不要要求用户确认本轮已明确的内容，不要为了模型选型、视频时长等参数暂停计划。'
        'ready 的 prompt 只能包含画面/动作/声音等生成内容，不得包含对用户的提问、确认语或过程说明。'
        '技能的问答和排版规则适用于 JSON 字段中的文字，不能覆盖此返回格式。'
    )})

    logger.info("调用 LLM 优化提示词...")

    # 只对“模型输出不合格”纠正一次；网络或供应商故障不在这里重复发送。
    # 第二次仍不合格时返回错误，由主图保存草稿，绝不把问题句提交到生成接口。
    for attempt in range(2):
        try:
            if attempt and on_retry:
                await on_retry()
            response = await llm_client.chat.completions.create(
                model=model_name or "gpt-4o-mini",
                messages=messages,
                response_format={"type": "json_object"},
            )
            if on_usage:
                await on_usage(response)
        except Exception:
            logger.exception("提示词优化模型请求失败")
            return {"error": "提示词优化服务暂不可用，请重试"}
        raw_content = None
        try:
            raw_content = response.choices[0].message.content
            parsed = PromptEnhancementResult.model_validate(json.loads(raw_content))
        except (ValueError, TypeError, AttributeError, IndexError) as error:
            logger.warning("提示词输出校验未通过 attempt=%d error=%s", attempt + 1, error)
            if attempt:
                return {"error": "模型两次未返回合格的最终提示词，已停止生成"}
            messages.extend([
                {"role": "assistant", "content": raw_content if isinstance(raw_content, str) else ""},
                {"role": "system", "content": (
                    f'上一结果校验失败：{error}。请按前述 JSON 协议纠正。'
                    '当前是实际生成任务的内部改写步骤，不是重新询问用户是否生成。'
                    '生成模型等参数将在面板中选择，不要追问；应输出通用的最终提示词。'
                    '确实缺少创作内容或必须的参考素材时，使用 needs_clarification，不能编造内容。'
                )},
            ])
            continue
        if parsed.status == "needs_clarification":
            logger.info("提示词优化需要补充信息 type=%s", parsed.clarification_type)
            return {"clarification": parsed.model_dump(exclude_none=True)}
        logger.info("提示词优化完成")
        return {"enhanced_prompt": parsed.prompt}


# ─────────────────────────────────────────────
# 子图工厂
# ─────────────────────────────────────────────

def create_prompt_enhance_subgraph(llm_client=None, model_name: Optional[str] = None, on_usage=None, on_retry=None):
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
        return await llm_enhance_node(
            state, llm_client=llm_client, model_name=model_name, on_usage=on_usage,
            on_retry=(lambda: on_retry(state)) if on_retry else None,
        )

    subgraph.add_node("analyze", analyze_need_node)
    subgraph.add_node("generate_ins", generate_instruction_node)
    subgraph.add_node("enhance", _llm_enhance)

    subgraph.set_entry_point("analyze")
    subgraph.add_edge("analyze", "generate_ins")
    subgraph.add_edge("generate_ins", "enhance")
    subgraph.add_edge("enhance", END)

    return subgraph.compile()
