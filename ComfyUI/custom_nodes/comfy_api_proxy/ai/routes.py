"""
Agent HTTP 路由
POST /api-proxy/agent/extract    — 角色/场景提取，SSE 流式
POST /api-proxy/agent/rewrite    — 剧本改写，SSE 流式
POST /api-proxy/agent/voice      — 音色分配，SSE 流式
POST /api-proxy/agent/storyboard — 分镜拆解，SSE 流式
"""
import json
import logging
from aiohttp import web
from aiohttp.web import StreamResponse
from server import PromptServer

from .graph import build_agent
from .rewriter.graph import build_rewrite_agent
from .voice.graph import build_voice_agent
from .storyboard.graph import build_storyboard_agent

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
                tool_input = event.get('data', {}).get('input', {})
                logger.info(f'[agent-extract] 工具调用: {name} 输入={tool_input}')
                await send('tool_start', {
                    'tool': name,
                    'input': tool_input,
                })

            elif kind == 'on_tool_end':
                output = event.get('data', {}).get('output', '')
                if hasattr(output, 'content'):
                    output = output.content
                logger.info(f'[agent-extract] 工具返回: {name} 输出={str(output)[:200]}')
                await send('tool_end', {
                    'tool': name,
                    'output': str(output)[:500],
                })

            elif kind == 'on_chat_model_stream':
                chunk = event.get('data', {}).get('chunk')
                if chunk and hasattr(chunk, 'content') and chunk.content:
                    final_text += chunk.content
                    logger.debug(f'[agent-extract] 模型输出: {chunk.content}')
                    await send('ai_message', {'text': chunk.content})

        logger.info(f'[agent-extract] 完成推理:\n{final_text.strip()}')
        await send('done', {'summary': final_text.strip()})
        logger.info(f'[agent-extract] 完成 episode_id={episode_id}')

    except Exception as e:
        logger.error(f'[agent-extract] 出错 episode_id={episode_id}: {e}')
        await send('error', {'message': str(e)})

    return resp


@routes.post('/api-proxy/agent/rewrite')
async def agent_rewrite(request: web.Request):
    """
    触发剧本改写 Agent，SSE 流式推送执行过程。

    请求体:
        {"episode_id": 1}

    SSE 事件类型:
        tool_start   — agent 开始调用某个工具
        tool_end     — 工具调用返回结果
        ai_message   — agent 的推理文字
        done         — 全部完成，附带最终摘要
        error        — 出错
    """
    body = await request.json()
    episode_id = body.get('episode_id')

    if not episode_id:
        raise web.HTTPBadRequest(reason='episode_id 为必填项')

    try:
        episode_id = int(episode_id)
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(reason='episode_id 必须为整数')

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
        agent = build_rewrite_agent(episode_id=episode_id)
        logger.info(f'[agent-rewrite] 开始 episode_id={episode_id}')

        final_text = ''
        async for event in agent.astream_events(
            {'messages': [('user', '请开始改写当前集剧本。')]},
            version='v2',
        ):
            kind = event.get('event', '')
            name = event.get('name', '')

            if kind == 'on_tool_start':
                tool_input = event.get('data', {}).get('input', {})
                logger.info(f'[agent-rewrite] 工具调用: {name} 输入={tool_input}')
                await send('tool_start', {
                    'tool': name,
                    'input': tool_input,
                })

            elif kind == 'on_tool_end':
                output = event.get('data', {}).get('output', '')
                if hasattr(output, 'content'):
                    output = output.content
                logger.info(f'[agent-rewrite] 工具返回: {name} 输出={str(output)[:200]}')
                await send('tool_end', {
                    'tool': name,
                    'output': str(output)[:500],
                })

            elif kind == 'on_chat_model_stream':
                chunk = event.get('data', {}).get('chunk')
                if chunk and hasattr(chunk, 'content') and chunk.content:
                    final_text += chunk.content
                    logger.debug(f'[agent-rewrite] 模型输出: {chunk.content}')
                    await send('ai_message', {'text': chunk.content})

        logger.info(f'[agent-rewrite] 完成推理:\n{final_text.strip()}')
        await send('done', {'summary': final_text.strip()})
        logger.info(f'[agent-rewrite] 完成 episode_id={episode_id}')

    except Exception as e:
        logger.error(f'[agent-rewrite] 出错 episode_id={episode_id}: {e}')
        await send('error', {'message': str(e)})

    return resp


@routes.post('/api-proxy/agent/voice')
async def agent_voice(request: web.Request):
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
        agent = build_voice_agent(episode_id=episode_id, drama_id=drama_id)
        logger.info(f'[agent-voice] 开始 episode_id={episode_id}')

        final_text = ''
        async for event in agent.astream_events(
            {'messages': [('user', '请开始为当前集的角色分配合适的音色。')]},
            version='v2',
        ):
            kind = event.get('event', '')
            name = event.get('name', '')

            if kind == 'on_tool_start':
                tool_input = event.get('data', {}).get('input', {})
                logger.info(f'[agent-voice] 工具调用: {name} 输入={tool_input}')
                await send('tool_start', {'tool': name, 'input': tool_input})

            elif kind == 'on_tool_end':
                output = event.get('data', {}).get('output', '')
                if hasattr(output, 'content'):
                    output = output.content
                logger.info(f'[agent-voice] 工具返回: {name} 输出={str(output)[:200]}')
                await send('tool_end', {'tool': name, 'output': str(output)[:500]})

            elif kind == 'on_chat_model_stream':
                chunk = event.get('data', {}).get('chunk')
                if chunk and hasattr(chunk, 'content') and chunk.content:
                    final_text += chunk.content
                    await send('ai_message', {'text': chunk.content})

        await send('done', {'summary': final_text.strip()})
        logger.info(f'[agent-voice] 完成 episode_id={episode_id}')

    except Exception as e:
        logger.error(f'[agent-voice] 出错 episode_id={episode_id}: {e}')
        await send('error', {'message': str(e)})

    return resp


@routes.post('/api-proxy/agent/storyboard')
async def agent_storyboard(request: web.Request):
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
        agent = build_storyboard_agent(episode_id=episode_id, drama_id=drama_id)
        logger.info(f'[agent-storyboard] 开始 episode_id={episode_id}')

        final_text = ''
        async for event in agent.astream_events(
            {'messages': [('user', '请开始对当前集剧本进行分镜拆解。')]},
            version='v2',
        ):
            kind = event.get('event', '')
            name = event.get('name', '')

            if kind == 'on_tool_start':
                tool_input = event.get('data', {}).get('input', {})
                logger.info(f'[agent-storyboard] 工具调用: {name} 输入={tool_input}')
                await send('tool_start', {'tool': name, 'input': tool_input})

            elif kind == 'on_tool_end':
                output = event.get('data', {}).get('output', '')
                if hasattr(output, 'content'):
                    output = output.content
                logger.info(f'[agent-storyboard] 工具返回: {name} 输出={str(output)[:200]}')
                await send('tool_end', {'tool': name, 'output': str(output)[:500]})

            elif kind == 'on_chat_model_stream':
                chunk = event.get('data', {}).get('chunk')
                if chunk and hasattr(chunk, 'content') and chunk.content:
                    final_text += chunk.content
                    await send('ai_message', {'text': chunk.content})

        await send('done', {'summary': final_text.strip()})
        logger.info(f'[agent-storyboard] 完成 episode_id={episode_id}')

    except Exception as e:
        logger.error(f'[agent-storyboard] 出错 episode_id={episode_id}: {e}')
        await send('error', {'message': str(e)})

    return resp
