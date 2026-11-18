"""
意图识别节点
"""
from typing import Dict, Any
from copy import deepcopy
import json
import logging
from agents.services.generation_plan import GenerationPlan

logger = logging.getLogger(__name__)


async def intent_recognition_node(state: Dict[str, Any], llm_client=None, model_name=None, on_usage=None) -> Dict[str, Any]:
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

    # 第一次模型调用只做分类并结构化生成计划；它不会提交生成任务。
    # 后续提示词优化节点会在 generation_plan 进入工具执行前逐步骤改写 prompt。
    model_messages = [{"role": "system", "content": (
        '结合对话历史判断用户最后一条消息的实际请求，只返回 JSON 对象：'
        '{"intent":"chat|txt2img|txt2video|generation_plan","prompt":"完整生成描述或空字符串","steps":[]}。'
        '只有用户明确要求实际生成图片或视频时，才选择 txt2img 或 txt2video。'
        '普通聊天、解释、图片问答、只编写提示词或脚本、明确不生成的请求都选 chat。'
        '例如“用 Seedance 优化视频提示词”属于 chat，选择技能不代表要求实际生成视频。'
        '回答“2.0”或“2.5”等确认问题时延续原任务；原任务只优化提示词时仍选 chat。'
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
    # 续接只让模型判断用户是否在回答追问，不让模型重建已保存的步骤和依赖。
    # 补充内容由后续优化节点结合对话应用；取消或换任务仍走正常分类。
    draft = state.get('generation_draft')
    if draft:
        model_messages.append({'role': 'system', 'content': (
            '当前有一份暂停的生成草稿。用户回答所问内容、补充素材、说“继续”或“重试”时，'
            '返回 {"intent":"resume_generation"}，服务端会恢复原任务，不需要重新输出步骤。'
            '用户明确取消、换话题、提出全新任务或要求重做之前已完成的步骤时，按正常分类返回，'
            '不要强行续接旧任务。草稿如下：' + json.dumps(draft, ensure_ascii=False)
        )})
    for message in messages:
        if isinstance(message, dict):
            role = message.get("role", "user")
            content = message.get("content", "")
        else:
            role = {'human': 'user', 'ai': 'assistant', 'system': 'system'}.get(message.type, message.type)
            content = message.content
        if isinstance(content, list):
            content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
        model_messages.append({"role": "assistant" if role == "agent" else role, "content": content})

    if any(message['role'] == 'system' for message in model_messages[1:]):
        model_messages.append({'role': 'system', 'content': (
            '本节点仅分类用户请求，必须遵循前述 JSON 格式。技能中的问答、排版规则用于后续回答；'
            '生成时把技能的创作要求应用于 prompt 或 steps 中的提示词，不能改变实际生成的判定条件。'
        )})

    response = await llm_client.chat.completions.create(
        model=model_name or "gpt-6.1-sol",
        messages=model_messages,
        response_format={"type": "json_object"},
        temperature=1,
    )
    if on_usage:
        await on_usage(response)
    try:
        result = json.loads(response.choices[0].message.content)
        if not isinstance(result, dict) or result.get("intent") not in ("chat", "txt2img", "txt2video", "generation_plan", "resume_generation"):
            raise ValueError("无效的请求类型")
        intent = result["intent"]
        if intent == 'resume_generation':
            if not draft:
                raise ValueError('没有可以恢复的生成草稿')
            request = deepcopy(draft['request'])
            # 用户本轮上传的素材只补到暂停步骤，不污染独立角色图或已完成步骤。
            target = next((step for step in request.get('steps', []) if step['id'] == draft['step_id']), request)
            if state.get('asset_ids'):
                target['input_asset_ids'] = list(dict.fromkeys([*target.get('input_asset_ids', []), *state['asset_ids']]))
            logger.info('恢复生成草稿 intent=%s step_id=%s', draft['intent'], draft.get('step_id'))
            return {'intent': draft['intent'], 'generation_request': request}
        prompt = result.get("prompt")
        if intent in ("txt2img", "txt2video") and (not isinstance(prompt, str) or not prompt.strip()):
            raise ValueError("缺少生成描述")
        if intent == 'generation_plan':
            # 在开始逐步优化之前验证依赖；无效计划不进入循环或参数确认。
            result['steps'] = GenerationPlan.model_validate({'steps': result.get('steps')}).model_dump(exclude_none=True)['steps']
    except (TypeError, ValueError) as error:
        raise ValueError("模型未返回有效的请求分类，请重试") from error

    logger.info("识别结果: intent=%s", intent)
    # generation_plan 的 steps 是计划草稿，后续仍需参数确认后才会持久化和排队。
    request = {"steps": result.get("steps")} if intent == "generation_plan" else ({"prompt": prompt} if intent != "chat" else None)
    return {"intent": intent, "generation_request": request, "generation_draft": None}
