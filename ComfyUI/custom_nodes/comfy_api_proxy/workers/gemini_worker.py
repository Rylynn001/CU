"""Gemini image generation worker using APIYI's native Gemini endpoint."""
import base64
import logging
import uuid

import requests

from .. import config as cfg
from ..repositories import asset_repo, history_repo
from ..services import task_queue

logger = logging.getLogger('comfy_api_proxy')
OUTPUT_DIR = cfg.get_output_dir()


def _api_root(base_url: str) -> str:
    root = base_url.rstrip('/')
    return root[:-3] if root.endswith('/v1') else root


def _save_history(task: dict, status: str, output_asset_ids: list[int], message: str | None = None):
    history_id = task.get('history_id')
    if history_id:
        history_repo.update_history(
            history_id=history_id,
            output_asset_ids=output_asset_ids,
            status=status,
            message=message,
        )
        return history_id
    return history_repo.save_history(
        task_id=task['task_id'],
        prompt=task.get('prompt', ''),
        user_id=int(task['user_id']) if task.get('user_id') else 0,
        model_id=int(task['model_id']) if task.get('model_id') else None,
        input_asset_ids=task.get('input_asset_ids', []),
        output_asset_ids=output_asset_ids,
        status=status,
        type_='img2img' if task.get('input_asset_ids') else 'txt2img',
        mode='api',
        message=message,
    )


def process(task: dict) -> None:
    task_id = task['task_id']
    try:
        task_queue.set_status(task_id, 'processing')
        logger.info('[%s] processing APIYI Gemini image task', task_id)

        quality_to_size = {'low': '1K', 'medium': '2K', 'high': '4K'}
        parts = [
            {'inlineData': {'mimeType': 'image/png', 'data': image}}
            for image in task.get('image_b64_list', [])
        ]
        parts.append({'text': task['prompt']})

        url = f"{_api_root(task['base_url'])}/v1beta/models/{task['model']}:generateContent"
        response = requests.post(
            url,
            headers={
                'Authorization': f"Bearer {task['api_key']}",
                'Content-Type': 'application/json',
            },
            json={
                'contents': [{'parts': parts}],
                'generationConfig': {
                    'responseModalities': ['IMAGE'],
                    'imageConfig': {
                        'aspectRatio': task.get('aspect_ratio', '1:1'),
                        'imageSize': quality_to_size.get(task.get('quality', 'medium'), '2K'),
                    },
                },
            },
            timeout=360,
        )
        response.raise_for_status()

        images = []
        save_paths = []
        for candidate in response.json().get('candidates', []):
            for part in candidate.get('content', {}).get('parts', []):
                inline = part.get('inlineData') or part.get('inline_data')
                if not inline or not inline.get('data'):
                    continue
                filename = f'Gemini-{uuid.uuid4().hex}.png'
                save_path = OUTPUT_DIR / filename
                save_path.write_bytes(base64.b64decode(inline['data']))
                images.append({
                    'url': f'/api/api-proxy/output/{filename}',
                    'type': 'image',
                    'asset_id': None,
                })
                save_paths.append(save_path)

        result_images = images[-1:]
        result_paths = save_paths[-1:]
        if not result_images:
            raise RuntimeError('No image generated')

        output_asset_ids = []
        user_id = task.get('user_id')
        if user_id:
            asset_id = asset_repo.save_output_asset(str(result_paths[0]), int(user_id), 'picture')
            output_asset_ids.append(asset_id)
            result_images[0]['asset_id'] = asset_id

        history_id = _save_history(task, 'done', output_asset_ids)
        task_queue.set_status(task_id, 'completed')
        task_queue.set_result(task_id, {'result': result_images, 'history_id': history_id})
        logger.info('[%s] Gemini image task completed', task_id)
    except Exception as error:
        logger.exception('[%s] Gemini image task failed', task_id)
        history_id = _save_history(task, 'error', [], str(error))
        task_queue.set_status(task_id, 'failed')
        task_queue.set_result(task_id, {
            'error': {'error_message': str(error)},
            'history_id': history_id,
        })
