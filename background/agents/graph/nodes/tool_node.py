"""准备生成请求，或把普通对话交给语言模型。"""
import logging

logger = logging.getLogger(__name__)


async def direct_execute_node(state, llm_client=None, model_name=None, on_usage=None):
    intent = state.get('intent')
    match intent:
        case 'txt2img' | 'txt2video' | 'generation_plan':
            return {'current_tool': intent, 'generation_request': state['generation_request']}
        case 'chat':
            if llm_client is None:
                return {'tool_result': {'error': '对话模型未初始化'}, 'is_complete': True}
            messages = []
            for message in state.get('messages', []):
                if isinstance(message, dict):
                    role, content = message.get('role', 'user'), message.get('content', '')
                else:
                    role, content = {'human': 'user', 'ai': 'assistant', 'system': 'system'}.get(message.type, message.type), message.content
                messages.append({'role': 'assistant' if role == 'agent' else role, 'content': content})
            try:
                response = await llm_client.chat.completions.create(
                    model=model_name or 'gpt-4o-mini', messages=messages,
                    max_completion_tokens=1024,
                )
                if on_usage:
                    await on_usage(response)
                reply = response.choices[0].message.content
                if not isinstance(reply, str) or not reply.strip():
                    raise ValueError('对话模型未返回有效回复，请重试')
                return {'tool_result': {'reply': reply}, 'is_complete': True}
            except Exception as error:
                logger.exception('对话生成失败')
                return {'tool_result': {'error': str(error) or '对话生成失败'}, 'is_complete': True}
        case _:
            return {'tool_result': {'error': '无法识别请求类型'}, 'is_complete': True}


async def execute_tool_node(state, workflow_tools=None):
    if workflow_tools is None:
        return {'tool_result': {'error': '工具执行器未初始化'}, 'is_complete': True}
    try:
        # 工具执行可能直接入队，也可能只返回 selection_required 等待用户补参数。
        result = await workflow_tools.discover_and_execute(state['current_tool'], state['generation_request'])
        return {'tool_result': result, 'is_complete': not bool(result.get('selection_required'))}
    except Exception as error:
        logger.exception('工具执行失败')
        return {'tool_result': {'error': str(error)}, 'is_complete': True}
