"""OpenAI 图片生成 worker"""
import json
import uuid
import time
import base64
import logging
import requests
import io
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config import settings
from database import execute_query
from repositories import history_repo

logger = logging.getLogger(__name__)

OUTPUT_DIR = pathlib.Path(settings.OUTPUT_DIR)


def _get_redis():
    """获取 Redis 客户端"""
    import redis
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True
    )


def _save_output_asset(location: str, user_id: int, asset_type: str) -> int:
    """保存输出资产到数据库"""
    query = """
        INSERT INTO assets (location, rfid, asset_type, created_at)
        VALUES (%s, %s, %s, NOW())
    """
    return execute_query(query, (location, user_id, asset_type))


def process(task: dict) -> None:
    task_id = task['task_id']
    redis_client = _get_redis()

    try:
        redis_client.setex(f"task:{task_id}:status", 3600, 'processing')
        logger.info(f'[{task_id}] 正在处理 OpenAI 任务')

        # 更新 history 表状态为 processing
        history_id = task.get('history_id')
        if history_id:
            history_repo.update_history(
                history_id=history_id,
                output_asset_ids=[],
                status='processing',
            )

        # 日志：记录接收到的任务参数（api_key 脱敏）
        api_key_masked = task['api_key'][:8] + '***' if len(task.get('api_key', '')) > 8 else '(empty or too short)'
        logger.info(f'[{task_id}] Worker 收到任务: model={task.get("model")}, '
                    f'provider={task.get("provider")}, api_key={api_key_masked}, '
                    f'base_url={task.get("base_url")}, prompt={task.get("prompt", "")[:50]}...')

        from openai import OpenAI

        client = OpenAI(api_key=task['api_key'], base_url=task['base_url'])

        n = task.get('n', 1)
        image_b64_list = task.get('image_b64_list', [])

        aspect_ratio_to_size = {
            '1:1':  '1024x1024',
            '16:9': '1792x1024',
            '9:16': '1024x1792',
            '4:3':  '1024x768',
            '3:4':  '768x1024',
        }
        size = aspect_ratio_to_size.get(task.get('aspect_ratio', '1:1'), '1024x1024')
        quality = task.get('quality', 'medium')

        response = None
        for attempt in range(3):
            try:
                if image_b64_list:
                    logger.info(f'[{task_id}] 调用 OpenAI images.edit，参考图数量={len(image_b64_list)}')
                    image_files = []
                    for idx, b64_str in enumerate(image_b64_list):
                        img_bytes = base64.b64decode(b64_str)
                        img_file = io.BytesIO(img_bytes)
                        img_file.name = f'image_{idx+1}.png'
                        image_files.append(img_file)

                    full_prompt = ''.join(f'图{idx+1}：' for idx in range(len(image_b64_list)))
                    full_prompt += task['prompt']

                    response = client.images.edit(
                        model=task['model'],
                        prompt=full_prompt,
                        image=image_files,
                        size=size,
                        quality=quality,
                        n=n,
                    )
                else:
                    logger.info(f'[{task_id}] 调用 OpenAI images.generate，model={task["model"]}, size={size}, quality={quality}, n={n}')
                    response = client.images.generate(
                        model=task['model'],
                        prompt=task['prompt'],
                        size=size,
                        quality=quality,
                        n=n,
                    )
                logger.info(f'[{task_id}] OpenAI API 调用成功')
                break
            except Exception as e:
                logger.warning(f'[{task_id}] 第 {attempt+1} 次尝试失败: {e}')
                if attempt < 2:
                    time.sleep(3)
                else:
                    raise

        images = []
        save_paths = []

        for img in response.data:
            img_data = None
            if hasattr(img, 'b64_json') and img.b64_json:
                img_data = base64.b64decode(img.b64_json)
            elif hasattr(img, 'url') and img.url:
                resp = requests.get(img.url, timeout=30)
                if resp.status_code == 200:
                    img_data = resp.content

            if img_data:
                filename = f'GPT-{uuid.uuid4().hex}.png'
                save_path = OUTPUT_DIR / filename
                with open(save_path, 'wb') as f:
                    f.write(img_data)
                images.append({'url': f'/api/api-proxy/output/{filename}', 'type': 'image', 'asset_id': None})
                save_paths.append(save_path)

        if not images:
            raise Exception('No image generated')

        output_asset_ids = []
        user_id = task.get('user_id')
        if user_id:
            for i, save_path in enumerate(save_paths):
                try:
                    aid = _save_output_asset(str(save_path), int(user_id), 'picture')
                    output_asset_ids.append(aid)
                    images[i]['asset_id'] = aid
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

        redis_client.setex(f"task:{task_id}:status", 3600, 'completed')
        redis_client.setex(f"task:{task_id}:result", 3600, json.dumps({'result': images, 'history_id': history_id}))
        logger.info(f'[{task_id}] 已完成，共 {len(images)} 张图片')

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
        redis_client.setex(f"task:{task_id}:status", 3600, 'failed')
        redis_client.setex(f"task:{task_id}:result", 3600, json.dumps({'error': {'error_message': str(e)}, 'history_id': history_id}))
