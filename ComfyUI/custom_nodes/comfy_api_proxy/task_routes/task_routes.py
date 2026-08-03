"""任务相关路由：txt2img / txt2video / img2video / task 状态查询"""
import uuid
import json
import base64
import logging
import pathlib
import asyncio
import aiohttp
from aiohttp import web
from server import PromptServer

from .. import config as cfg
from ..repositories import provider_repo as db_queries
from ..services import task_queue, provider_service
from ..repositories import asset_repo, history_repo

logger = logging.getLogger('comfy_api_proxy')
routes = PromptServer.instance.routes

OUTPUT_DIR = cfg.get_output_dir()
QUEUE_MAX_SIZE = cfg.get_queue_max_size()


def _load_input_assets_as_b64(input_asset_ids: list[int]) -> list[str]:
    """批量读取参考图文件，返回 base64 列表"""
    result = []
    assets = asset_repo.get_assets_by_ids(input_asset_ids)
    asset_map = {a['id']: a for a in assets}
    for asset_id in input_asset_ids:
        asset = asset_map.get(asset_id)
        if not asset:
            raise web.HTTPNotFound(reason=f'asset {asset_id} not found')
        file_path = pathlib.Path(asset['location'])
        if not file_path.exists():
            raise web.HTTPNotFound(reason=f'file not found: {asset["location"]}')
        result.append(base64.b64encode(file_path.read_bytes()).decode())
    return result


def _update_history_from_redis(task_id: str, output_asset_ids: list, status: str, message: str | None = None) -> int | None:
    """从 Redis 读取 history_id，更新已有历史记录"""
    try:
        history_id_raw = task_queue.get_meta(task_id, 'history_id')
        if not history_id_raw:
            logger.warning(f'[history] 任务 {task_id} 无 history_id，跳过更新')
            return None
        history_id = int(history_id_raw)
        history_repo.update_history(
            history_id=history_id,
            output_asset_ids=output_asset_ids,
            status=status,
            message=message,
        )
        return history_id
    except Exception as e:
        logger.error(f'[history] 任务 {task_id} 更新历史记录失败: {e}')
        return None


async def _download_video(task_id: str, video_url: str, stored_user_id: str | None) -> tuple[str, int | None]:
    """下载视频到 OUTPUT_DIR，写入 assets 表，返回 (local_url, asset_id)"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.mp4'
    save_path = OUTPUT_DIR / filename

    async with aiohttp.ClientSession() as session:
        async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=600)) as resp:
            if resp.status != 200:
                raise Exception(f'Failed to download video: {resp.status}')
            with open(save_path, 'wb') as f:
                f.write(await resp.read())

    local_url = f'/api/api-proxy/output/{filename}'
    logger.info(f'[{task_id}] 视频已保存至 {save_path}')

    output_asset_id = None
    if stored_user_id:
        try:
            output_asset_id = asset_repo.save_output_asset(str(save_path), int(stored_user_id), 'video')
            logger.info(f'[{task_id}] 已写入资产表（视频）')
        except Exception as e:
            logger.error(f'[{task_id}] 数据库写入失败: {e}')

    return local_url, output_asset_id


async def _poll_ark_task(task_id: str, remote_id: str, api_key: str, base_url: str | None, stored_user_id: str | None):
    """轮询 Ark 任务状态，完成后下载视频并更新 Redis"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        result = client.get(f"/contents/generations/tasks/{remote_id}", cast_to=object)
        remote_status = result.get("status")
        logger.info(f'[{task_id}] Ark 状态: {remote_status}')

        if remote_status == "succeeded":
            video_url = result.get("content", {}).get("video_url")
            if not video_url:
                raise Exception('No video URL in result')

            task_queue.set_downloading_lock(task_id)
            try:
                local_url, output_asset_id = await _download_video(task_id, video_url, stored_user_id)
                history_id = _update_history_from_redis(
                    task_id, [output_asset_id] if output_asset_id else [], status='done'
                )

                # 查询参考图 URL，随结果一起返回给前端
                input_asset_urls = []
                try:
                    input_ids_raw = task_queue.get_meta(task_id, 'input_asset_ids')
                    input_ids = json.loads(input_ids_raw) if input_ids_raw else []
                    if input_ids:
                        in_assets = asset_repo.get_assets_by_ids(input_ids)
                        asset_map = {a['id']: a for a in in_assets}
                        for aid in input_ids:
                            if aid in asset_map:
                                filename = pathlib.Path(asset_map[aid]['location']).name
                                ext = pathlib.Path(filename).suffix.lower()
                                asset_type = 'video' if ext in ('.mp4', '.mov', '.avi', '.webm') else 'image'
                                input_asset_urls.append({'url': f'/api/api-proxy/output/{filename}', 'type': asset_type})
                except Exception as e:
                    logger.warning(f'[{task_id}] 查询参考图失败: {e}')

                task_queue.set_status(task_id, 'completed')
                task_queue.set_result(task_id, {
                    'result': [{'url': local_url, 'type': 'video', 'asset_id': output_asset_id}],
                    'history_id': history_id,
                    'input_asset_urls': input_asset_urls,
                })
                task_queue.delete_meta(task_id, 'remote_id', 'api_key', 'base_url', 'provider', 'user_id')
                task_queue.release_downloading_lock(task_id)
                return web.json_response({
                    'status': 'completed',
                    'result': [{'url': local_url, 'type': 'video', 'asset_id': output_asset_id}],
                    'history_id': history_id,
                })
            except Exception as download_error:
                task_queue.release_downloading_lock(task_id)
                raise download_error

        elif remote_status == "failed":
            error_info = result.get("error") if isinstance(result, dict) else None
            error_msg = (error_info.get("message") if isinstance(error_info, dict) else None) or "Video generation failed"
            logger.error(f'[{task_id}] Ark 任务失败: {error_msg}，完整响应: {result}')
            _update_history_from_redis(task_id, [], status='error', message=error_msg)
            task_queue.set_status(task_id, 'failed')
            task_queue.set_result(task_id, {'error': {'error_message': error_msg}})
            return web.json_response({'status': 'failed', 'error': {'error_message': error_msg}})

    except Exception as e:
        logger.error(f'[{task_id}] 查询 Ark 状态失败: {e}')

    return None


# ── /api-proxy/txt2img ────────────────────────────────────────────────────

@routes.post('/api-proxy/txt2img')
async def txt2img(request: web.Request):
    body = await request.json()

    model_id = body.get('model')
    prompt = body.get('prompt', '').strip()
    aspect_ratio = body.get('aspect_ratio', '1:1')
    quality = body.get('quality', 'medium')
    n = body.get('n', 1)
    input_asset_ids = body.get('input_asset_ids', [])
    user_id = body.get('user_id')

    if not model_id:
        raise web.HTTPBadRequest(reason='model is required')
    if not prompt:
        raise web.HTTPBadRequest(reason='prompt is required')

    provider_id = body.get('provider_id')
    api_key, base_url = provider_service.get_provider_config(provider_id=provider_id, model_id=model_id)
    model_info = provider_service.get_model_info(model_id)
    model_name = model_info['name']

    image_b64_list = _load_input_assets_as_b64(input_asset_ids) if input_asset_ids else []

    provider = model_info.get('provider', '')
    if not provider:
        raise web.HTTPBadRequest(reason=f'model {model_id} 未配置 provider 字段')
    logger.info(f'[api-proxy] txt2img model={model_name} provider={provider} prompt={prompt[:50]}')

    if provider not in ('openai', 'gemini'):
        raise web.HTTPBadRequest(reason=f'Unsupported provider: {provider}')

    if not task_queue.AVAILABLE:
        raise web.HTTPServiceUnavailable(reason='Redis not available')

    if task_queue.queue_length('queue:txt2img') >= QUEUE_MAX_SIZE:
        raise web.HTTPServiceUnavailable(reason=f'系统繁忙，请稍后再试')

    task_id = str(uuid.uuid4())
    type_ = 'img2img' if input_asset_ids else 'txt2img'
    history_id = history_repo.save_history(
        task_id=task_id,
        prompt=prompt,
        user_id=int(user_id) if user_id else 0,
        model_id=int(model_id) if model_id else None,
        input_asset_ids=input_asset_ids,
        output_asset_ids=[],
        status='pending',
        type_=type_,
        mode='api',
        payload={'model': model_id, 'prompt': prompt, 'aspect_ratio': aspect_ratio, 'quality': quality, 'n': n, 'input_asset_ids': input_asset_ids, 'user_id': user_id},
    )

    task_payload = {
        'task_id': task_id,
        'provider': provider,
        'model': model_name,
        'model_id': model_id,
        'prompt': prompt,
        'aspect_ratio': aspect_ratio,
        'quality': quality,
        'n': n,
        'user_id': user_id,
        'api_key': api_key,
        'base_url': base_url,
        'image_b64_list': image_b64_list,
        'input_asset_ids': input_asset_ids,
        'history_id': history_id,
    }

    task_queue.enqueue('queue:txt2img', task_payload)
    task_queue.mark_pending(task_id)
    logger.info(f'[api-proxy] txt2img 任务已入队: {task_id}')
    return web.json_response({'task_id': task_id, 'history_id': history_id})


# ── /api-proxy/txt2video ──────────────────────────────────────────────────

@routes.post('/api-proxy/txt2video')
async def txt2video(request: web.Request):
    body = await request.json()

    model_id = body.get('model')
    prompt = body.get('prompt', '').strip()

    if not model_id:
        raise web.HTTPBadRequest(reason='model is required')
    if not prompt:
        raise web.HTTPBadRequest(reason='prompt is required')

    provider_id = body.get('provider_id')
    api_key, base_url = provider_service.get_provider_config(provider_id=provider_id, model_id=model_id)
    model_info = provider_service.get_model_info(model_id)
    model_name = model_info['name']

    logger.info(f'[api-proxy] txt2video model={model_name} prompt={prompt[:50]}')

    if not task_queue.AVAILABLE:
        raise web.HTTPServiceUnavailable(reason='Redis not available')

    if task_queue.queue_length('queue:txt2video') >= QUEUE_MAX_SIZE:
        raise web.HTTPServiceUnavailable(reason=f'系统繁忙，请稍后再试')

    task_id = str(uuid.uuid4())
    user_id = body.get('user_id')
    history_id = history_repo.save_history(
        task_id=task_id,
        prompt=prompt,
        user_id=int(user_id) if user_id else 0,
        model_id=int(model_id) if model_id else None,
        input_asset_ids=[],
        output_asset_ids=[],
        status='pending',
        type_='txt2video',
        mode='api',
        payload={'model': model_id, 'prompt': prompt, 'ratio': body.get('ratio', '16:9'), 'resolution': body.get('resolution', '720p'), 'duration': body.get('duration', 8), 'user_id': user_id},
    )

    task_payload = {
        'task_id': task_id,
        'provider': 'ark',
        'model': model_name,
        'model_id': model_id,
        'prompt': prompt,
        'ratio': body.get('ratio', '16:9'),
        'resolution': body.get('resolution', '720p'),
        'duration': body.get('duration', 8),
        'user_id': user_id,
        'api_key': api_key,
        'base_url': base_url,
        'history_id': history_id,
    }

    task_queue.enqueue('queue:txt2video', task_payload)
    task_queue.mark_pending(task_id)
    logger.info(f'[api-proxy] txt2video 任务已入队: {task_id}')
    return web.json_response({'task_id': task_id, 'history_id': history_id})


# ── /api-proxy/img2video ──────────────────────────────────────────────────

@routes.post('/api-proxy/img2video')
async def img2video(request: web.Request):
    body = await request.json()

    model_id = body.get('model')
    prompt = (body.get('prompt') or '').strip()

    if not model_id:
        raise web.HTTPBadRequest(reason='model is required')
    if not prompt:
        raise web.HTTPBadRequest(reason='prompt is required')

    provider_id = body.get('provider_id')
    api_key, base_url = provider_service.get_provider_config(provider_id=provider_id, model_id=model_id)
    model_info = provider_service.get_model_info(model_id)
    model_name = model_info['name']

    logger.info(f'[api-proxy] img2video model={model_name} prompt={prompt[:50]}')

    if not task_queue.AVAILABLE:
        raise web.HTTPServiceUnavailable(reason='Redis not available')

    if task_queue.queue_length('queue:img2video') >= QUEUE_MAX_SIZE:
        raise web.HTTPServiceUnavailable(reason=f'系统繁忙，请稍后再试')

    input_asset_ids = body.get('input_asset_ids') or []
    if isinstance(input_asset_ids, str):
        input_asset_ids = [int(x.strip()) for x in input_asset_ids.split(',') if x.strip()]

    user_id = body.get('user_id')
    task_id = str(uuid.uuid4())
    history_id = history_repo.save_history(
        task_id=task_id,
        prompt=prompt,
        user_id=int(user_id) if user_id else 0,
        model_id=int(model_id) if model_id else None,
        input_asset_ids=input_asset_ids,
        output_asset_ids=[],
        status='pending',
        type_='img2video',
        mode='api',
        payload={'model': model_id, 'prompt': prompt, 'ratio': body.get('ratio', '16:9'), 'resolution': body.get('resolution', '720p'), 'duration': int(body.get('duration', 8)), 'input_asset_ids': input_asset_ids, 'user_id': user_id},
    )

    task_payload = {
        'task_id': task_id,
        'provider': 'ark',
        'model': model_name,
        'model_id': model_id,
        'prompt': prompt,
        'ratio': body.get('ratio', '16:9'),
        'resolution': body.get('resolution', '720p'),
        'duration': int(body.get('duration', 8)),
        'user_id': user_id,
        'api_key': api_key,
        'base_url': base_url,
        'input_asset_ids': input_asset_ids,
        'history_id': history_id,
    }

    task_queue.enqueue('queue:img2video', task_payload)
    task_queue.mark_pending(task_id)
    logger.info(f'[api-proxy] img2video 任务已入队: {task_id}')
    return web.json_response({'task_id': task_id, 'history_id': history_id})


# ── /api-proxy/task/{task_id} ─────────────────────────────────────────────

@routes.get('/api-proxy/task/{task_id}')
async def get_task_status(request: web.Request):
    task_id = request.match_info['task_id']

    if not task_queue.AVAILABLE:
        raise web.HTTPServiceUnavailable(reason='Redis not available')

    status = task_queue.get_status(task_id)
    if not status:
        raise web.HTTPNotFound(reason=f'Task {task_id} not found or expired.')

    logger.info(f'[api-proxy] 任务 {task_id} 状态: {status}')

    if status == 'processing':
        remote_id = task_queue.get_meta(task_id, 'remote_id')
        if remote_id and not task_queue.is_downloading(task_id):
            provider = task_queue.get_meta(task_id, 'provider')
            api_key = task_queue.get_meta(task_id, 'api_key')
            stored_user_id = task_queue.get_meta(task_id, 'user_id')

            if provider == 'ark':
                base_url = task_queue.get_meta(task_id, 'base_url')
                poll_result = await _poll_ark_task(task_id, remote_id, api_key, base_url, stored_user_id)
                if poll_result:
                    return poll_result

        return web.json_response({'status': 'processing'})

    response = {'status': status}
    if status in ('completed', 'failed'):
        result_data = task_queue.get_result(task_id)
        if result_data:
            if status == 'completed':
                response['result'] = result_data.get('result', [])
                if result_data.get('history_id'):
                    response['history_id'] = result_data['history_id']
                input_asset_urls = result_data.get('input_asset_urls')
                if input_asset_urls:
                    response['input_asset_urls'] = input_asset_urls
            else:
                response['error'] = result_data.get('error')
                if result_data.get('history_id'):
                    response['history_id'] = result_data['history_id']

    return web.json_response(response)


# ── /api-proxy/history/{history_id}/retry ────────────────────────────────

@routes.post('/api-proxy/history/{history_id}/retry')
async def retry_history(request: web.Request):
    history_id = int(request.match_info['history_id'])

    row = history_repo.get_history_by_id(history_id)
    if not row:
        raise web.HTTPNotFound(reason=f'history {history_id} not found')

    payload_raw = row.get('payload')
    if not payload_raw:
        raise web.HTTPBadRequest(reason='该记录没有保存 payload，无法重试')

    payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
    type_ = row.get('type', '')
    model_id = payload.get('model')
    prompt = payload.get('prompt', '')
    user_id = payload.get('user_id')

    if not task_queue.AVAILABLE:
        raise web.HTTPServiceUnavailable(reason='Redis not available')

    provider_id = None
    api_key, base_url = provider_service.get_provider_config(provider_id=provider_id, model_id=model_id)
    model_info = provider_service.get_model_info(model_id)
    model_name = model_info['name']

    new_task_id = str(uuid.uuid4())

    if type_ in ('txt2img', 'img2img'):
        if task_queue.queue_length('queue:txt2img') >= QUEUE_MAX_SIZE:
            raise web.HTTPServiceUnavailable(reason='系统繁忙，请稍后再试')

        input_asset_ids = payload.get('input_asset_ids', [])
        image_b64_list = _load_input_assets_as_b64(input_asset_ids) if input_asset_ids else []
        provider = model_info.get('provider', '')
        if not provider:
            raise web.HTTPBadRequest(reason=f'model {model_id} 未配置 provider 字段')

        new_history_id = history_repo.save_history(
            task_id=new_task_id,
            prompt=prompt,
            user_id=int(user_id) if user_id else 0,
            model_id=int(model_id) if model_id else None,
            input_asset_ids=input_asset_ids,
            output_asset_ids=[],
            status='pending',
            type_=type_,
            mode='api',
            payload=payload,
        )
        task_payload = {
            'task_id': new_task_id,
            'provider': provider,
            'model': model_name,
            'model_id': model_id,
            'prompt': prompt,
            'aspect_ratio': payload.get('aspect_ratio', '1:1'),
            'quality': payload.get('quality', 'medium'),
            'n': payload.get('n', 1),
            'user_id': user_id,
            'api_key': api_key,
            'base_url': base_url,
            'image_b64_list': image_b64_list,
            'input_asset_ids': input_asset_ids,
            'history_id': new_history_id,
        }
        task_queue.enqueue('queue:txt2img', task_payload)

    elif type_ == 'txt2video':
        if task_queue.queue_length('queue:txt2video') >= QUEUE_MAX_SIZE:
            raise web.HTTPServiceUnavailable(reason='系统繁忙，请稍后再试')

        new_history_id = history_repo.save_history(
            task_id=new_task_id,
            prompt=prompt,
            user_id=int(user_id) if user_id else 0,
            model_id=int(model_id) if model_id else None,
            input_asset_ids=[],
            output_asset_ids=[],
            status='pending',
            type_='txt2video',
            mode='api',
            payload=payload,
        )
        task_payload = {
            'task_id': new_task_id,
            'provider': 'ark',
            'model': model_name,
            'model_id': model_id,
            'prompt': prompt,
            'ratio': payload.get('ratio', '16:9'),
            'resolution': payload.get('resolution', '720p'),
            'duration': payload.get('duration', 8),
            'user_id': user_id,
            'api_key': api_key,
            'base_url': base_url,
            'history_id': new_history_id,
        }
        task_queue.enqueue('queue:txt2video', task_payload)

    elif type_ == 'img2video':
        if task_queue.queue_length('queue:img2video') >= QUEUE_MAX_SIZE:
            raise web.HTTPServiceUnavailable(reason='系统繁忙，请稍后再试')

        input_asset_ids = payload.get('input_asset_ids', [])
        new_history_id = history_repo.save_history(
            task_id=new_task_id,
            prompt=prompt,
            user_id=int(user_id) if user_id else 0,
            model_id=int(model_id) if model_id else None,
            input_asset_ids=input_asset_ids,
            output_asset_ids=[],
            status='pending',
            type_='img2video',
            mode='api',
            payload=payload,
        )
        task_payload = {
            'task_id': new_task_id,
            'provider': 'ark',
            'model': model_name,
            'model_id': model_id,
            'prompt': prompt,
            'ratio': payload.get('ratio', '16:9'),
            'resolution': payload.get('resolution', '720p'),
            'duration': int(payload.get('duration', 8)),
            'user_id': user_id,
            'api_key': api_key,
            'base_url': base_url,
            'input_asset_ids': input_asset_ids,
            'history_id': new_history_id,
            'input_files': [],
        }
        task_queue.enqueue('queue:img2video', task_payload)

    else:
        raise web.HTTPBadRequest(reason=f'不支持的任务类型: {type_}')

    task_queue.mark_pending(new_task_id)
    history_repo.soft_delete_history(history_id)
    logger.info(f'[retry] history {history_id} → new task {new_task_id}, type={type_}')
    return web.json_response({'task_id': new_task_id, 'history_id': new_history_id})




@routes.post('/api-proxy/task/{task_id}/cancel')
async def cancel_task(request: web.Request):
    task_id = request.match_info['task_id']

    if not task_queue.AVAILABLE:
        raise web.HTTPServiceUnavailable(reason='Redis not available')

    task_queue.set_status(task_id, 'failed')
    task_queue.set_result(task_id, {'error': {'error_message': '任务已被用户取消'}})
    logger.info(f'[api-proxy] 任务 {task_id} 已取消')
    return web.json_response({'ok': True})


# ── /api-proxy/task/{task_id}/priority ────────────────────────────────────

@routes.post('/api-proxy/task/{task_id}/priority')
async def prioritize_task(request: web.Request):
    task_id = request.match_info['task_id']

    if not task_queue.AVAILABLE:
        raise web.HTTPServiceUnavailable(reason='Redis not available')

    status = task_queue.get_status(task_id)
    if not status:
        raise web.HTTPNotFound(reason='Task not found')
    if status != 'pending':
        raise web.HTTPBadRequest(reason=f'Task is {status}, cannot prioritize')

    provider = task_queue.get_meta(task_id, 'provider')
    if provider == 'ark':
        remote_id = task_queue.get_meta(task_id, 'remote_id')
        queue_name = 'queue:img2video' if remote_id else 'queue:txt2video'
    else:
        queue_name = 'queue:txt2img'

    items = task_queue.list_queue(queue_name)
    found = False
    for item in items:
        if item.get('task_id') == task_id:
            item_json = json.dumps(item)
            task_queue.remove_from_queue(queue_name, item_json)
            task_queue.push_to_front(queue_name, item_json)
            found = True
            logger.info(f'[api-proxy] 任务 {task_id} 已提升优先级至队列 {queue_name}')
            break

    if not found:
        raise web.HTTPNotFound(reason='Task not found in queue')

    return web.json_response({'ok': True})
