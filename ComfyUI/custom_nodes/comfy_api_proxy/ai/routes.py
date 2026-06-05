"""
角色/场景提取 Agent HTTP 路由
POST /api-proxy/agent/extract  — SSE 流式返回 agent 执行过程
"""
import json
import logging
from aiohttp import web
from aiohttp.web import StreamResponse
from server import PromptServer

from .graph import build_agent

logger = logging.getLogger('comfy_api_proxy')
routes = PromptServer.instance.routes


@routes.post('/api-proxy/agent/extract')
async def agent_extract(request: web.Request):
    """
    触发角色/场景提取 Agent，SSE 流式推送执行过程。

    请求体:
        {"episode_id": 1, "drama_id": 1}

    SSE 事件类型:
        tool_start   — agent 开始调用某个工具
        tool_end     — 工具调用返回结果
        ai_message   — agent 的推理文字
        done         — 全部完成，附带最终摘要
        error        — 出错
    """
    body = await request.json()
    episode_id = body.get('episode_id')
    drama_id = body.get('drama_id')

    if not episode_id or not drama_id:
        raise web.HTTPBadRequest(reason='episode_id 和 drama_id 为必填项')

    try:
        episode_id = int(episode_id)
        drama_id = int(drama_id)
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(reason='episode_id 和 drama_id 必须为整数')

    resp = StreamResponse(headers={
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
    })
    await resp.prepare(request)

    async def send(event: str, data: dict):
        payload = f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'
        await resp.write(payload.encode('utf-8'))

    try:
        agent = build_agent(episode_id=episode_id, drama_id=drama_id)
        logger.info(f'[agent-extract] 开始 episode_id={episode_id} drama_id={drama_id}')

        final_text = ''
        async for event in agent.astream_events(
            {'messages': [('user', '请开始提取当前集的角色和场景。')]},
            version='v2',
        ):
            kind = event.get('event', '')
            name = event.get('name', '')

            if kind == 'on_tool_start':
                await send('tool_start', {
                    'tool': name,
                    'input': event.get('data', {}).get('input', {}),
                })

            elif kind == 'on_tool_end':
                output = event.get('data', {}).get('output', '')
                if hasattr(output, 'content'):
                    output = output.content
                await send('tool_end', {
                    'tool': name,
                    'output': str(output)[:500],
                })

            elif kind == 'on_chat_model_stream':
                chunk = event.get('data', {}).get('chunk')
                if chunk and hasattr(chunk, 'content') and chunk.content:
                    final_text += chunk.content
                    await send('ai_message', {'text': chunk.content})

        await send('done', {'summary': final_text.strip()})
        logger.info(f'[agent-extract] 完成 episode_id={episode_id}')

    except Exception as e:
        logger.error(f'[agent-extract] 出错 episode_id={episode_id}: {e}')
        await send('error', {'message': str(e)})

    return resp
