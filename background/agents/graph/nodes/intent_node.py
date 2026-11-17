"""
意图识别节点
"""
from typing import Dict, Any
import json
import logging

logger = logging.getLogger(__name__)


async def intent_recognition_node(state: Dict[str, Any], llm_client=None, model_name=None) -> Dict[str, Any]:
    """
    识别用户意图

    Args:
        state: ConversationState

    Returns:
        更新的状态，包含 intent 字段
    """
    messages = state.get("messages", [])
    if not messages:
        raise ValueError("消息列表为空，无法识别请求")
    if llm_client is None:
        raise ValueError("对话模型未初始化")

    # 路由只读取文字和历史，图片内容仍交给实际对话节点处理。
    model_messages = [{"role": "system", "content": (
        '结合对话历史判断用户最后一条消息的实际请求，只返回 JSON 对象：'
        '{"intent":"chat|txt2img|txt2video|generation_plan","prompt":"完整生成描述或空字符串","steps":[]}。'
        '只有用户明确要求实际生成图片或视频时，才选择 txt2img 或 txt2video。'
        '普通聊天、解释、图片问答、只编写提示词或脚本、明确不生成的请求都选 chat。'
        '不要仅因为出现图片、视频等词就判定为生成。'
        '例如“这张图片有什么问题”“不要生成视频，只解释一下”都属于 chat。'
        '“按刚才的描述来一张”需结合历史判断为 txt2img，并在 prompt 中还原完整描述。'
        '生成描述必须忠实于用户要求，不得编造模型、比例、数量等未确认参数。'
        '需要多次生成或中间结果作为下一步参考时，选择 generation_plan，并输出 2 到 12 个步骤。'
        '每个步骤格式：{"id":"s1","label":"步骤名称","media_type":"image|video",'
        '"prompt":"独立完整的生成描述","depends_on":[],"input_asset_ids":[]}。'
        'depends_on 只能填写前面步骤的 id，表示把这些步骤的输出作为参考素材；独立步骤不应添加依赖。'
        'input_asset_ids 只填写上下文明确提供的真实资产编号，不得把步骤编号当成资产编号。'
        '用户指定视频秒数时在该视频步骤中额外填写 duration。不得把整项任务合并成单次生成。'
        '例如生成男主和女主、两人合影、合影生成8秒视频：四个步骤，合影依赖两个角色图，视频依赖合影。'
        '人物、场景等描述应在对应步骤写完整，保持角色身份；只要求方案时仍属于 chat。'
        '不能确定用户是否要求实际生成时选 chat，由后续对话澄清。'
    )}]
    for message in messages:
        if isinstance(message, dict):
            role = message.get("role", "user")
            content = message.get("content", "")
        else:
            role = "user" if message.type == "human" else "assistant"
            content = message.content
        if isinstance(content, list):
            content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
        model_messages.append({"role": "assistant" if role == "agent" else role, "content": content})

    response = await llm_client.chat.completions.create(
        model=model_name or "gpt-4o-mini",
        messages=model_messages,
        response_format={"type": "json_object"},
        temperature=0,
    )
    try:
        result = json.loads(response.choices[0].message.content)
        if not isinstance(result, dict) or result.get("intent") not in ("chat", "txt2img", "txt2video", "generation_plan"):
            raise ValueError("无效的请求类型")
        intent = result["intent"]
        prompt = result.get("prompt")
        if intent in ("txt2img", "txt2video") and (not isinstance(prompt, str) or not prompt.strip()):
            raise ValueError("缺少生成描述")
    except (TypeError, ValueError) as error:
        raise ValueError("模型未返回有效的请求分类，请重试") from error

    logger.info("识别结果: intent=%s", intent)
    request = {"steps": result.get("steps")} if intent == "generation_plan" else ({"prompt": prompt} if intent != "chat" else None)
    return {"intent": intent, "generation_request": request}
