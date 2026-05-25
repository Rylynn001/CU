"""Gemini 图片生成 worker"""
import uuid
import base64
import logging
import shutil
import tempfile
import os
from .. import config as cfg
from ..repositories import asset_repo, history_repo
from ..services import task_queue

logger = logging.getLogger('comfy_api_proxy')

OUTPUT_DIR = cfg.get_output_dir()


def process(task: dict) -> None:
    task_id = task['task_id']
    try:
        task_queue.set_status(task_id, 'processing')
        logger.info(f'[{task_id}] 正在处理 Gemini 任务')

        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(
            vertexai=True,
            api_key=task['api_key'],
            http_options={'base_url': task['base_url']}
        )

        image_b64_list = task.get('image_b64_list', [])
        prompt = task['prompt']

        if image_b64_list:
            contents = []
            for i, b64 in enumerate(image_b64_list):
                contents.append(genai_types.Part.from_text(text=f'图{i+1}：'))
                contents.append(genai_types.Part.from_bytes(
                    data=base64.b64decode(b64), mime_type='image/png'
                ))
            contents.append(genai_types.Part.from_text(text=prompt))
        else:
            contents = prompt

        response = client.models.generate_content(
            model=task['model'],
            contents=contents
        )

        images = []
        save_paths = []
        if hasattr(response, 'parts'):
            for part in response.parts:
                if hasattr(part, 'as_image'):
                    image = part.as_image()
                    if image:
                        filename = f'{uuid.uuid4().hex}.png'
                        save_path = OUTPUT_DIR / filename
                        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                            tmp_path = tmp.name
                        try:
                            image.save(tmp_path)
                            shutil.move(tmp_path, str(save_path))
                        except Exception:
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
                            raise
                        images.append({'url': f'/api/api-proxy/output/{filename}', 'type': 'image'})
                        save_paths.append(save_path)

        # 只取最后一张（避免返回输入图）
        result_images = images[-1:] if images else []
        result_paths = save_paths[-1:] if save_paths else []

        if not result_images:
            raise Exception('No image generated')

        output_asset_ids = []
        user_id = task.get('user_id')
        if user_id and result_paths:
            try:
                aid = asset_repo.save_output_asset(str(result_paths[0]), int(user_id), 'picture')
                output_asset_ids.append(aid)
            except Exception as e:
                logger.error(f'[{task_id}] 数据库写入失败: {e}')

        type_ = 'img2img' if task.get('input_asset_ids') else 'txt2img'
        history_id = task.get('history_id')
        if history_id:
            history_repo.update_history(
                history_id=history_id,
                output_asset_ids=output_asset_ids,
                status='done',
            )
        else:
            history_id = history_repo.save_history(
                task_id=task_id,
                prompt=task.get('prompt', ''),
                user_id=int(user_id) if user_id else 0,
                model_id=int(task['model_id']) if task.get('model_id') else None,
                input_asset_ids=task.get('input_asset_ids', []),
                output_asset_ids=output_asset_ids,
                status='done',
                type_=type_,
                mode='api',
            )

        task_queue.set_status(task_id, 'completed')
        task_queue.set_result(task_id, {'result': result_images, 'history_id': history_id})
        logger.info(f'[{task_id}] 已完成，共 {len(result_images)} 张图片')

    except Exception as e:
        logger.error(f'[{task_id}] 任务失败: {e}')
        type_ = 'img2img' if task.get('input_asset_ids') else 'txt2img'
        history_id = task.get('history_id')
        if history_id:
            history_repo.update_history(history_id=history_id, output_asset_ids=[], status='error', message=str(e))
        else:
            history_repo.save_history(
                task_id=task_id,
                prompt=task.get('prompt', ''),
                user_id=int(task['user_id']) if task.get('user_id') else 0,
                model_id=int(task['model_id']) if task.get('model_id') else None,
                input_asset_ids=task.get('input_asset_ids', []),
                output_asset_ids=[],
                status='error',
                type_=type_,
                mode='api',
                message=str(e),
            )
        task_queue.set_status(task_id, 'failed')
        task_queue.set_result(task_id, {'error': {'error_message': str(e)}})
