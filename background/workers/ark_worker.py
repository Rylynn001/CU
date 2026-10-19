"""Ark (火山引擎) 视频生成 worker - 只提交任务，不轮询"""
import json
import time
import logging
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config import settings
from database import execute_query
from repositories import history_repo
from core import parse_provider_error

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


def process_txt2video(task: dict) -> None:
    """提交文生视频任务到 Ark，保存 remote_id 等待轮询"""
    task_id = task['task_id']
    redis_client = _get_redis()

    try:
        redis_client.setex(f"task:{task_id}:status", 3600, 'processing')
        logger.info(f'[{task_id}] 正在处理 Ark 文生视频任务')

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
                    f'base_url={task.get("base_url")}, '
                    f'ratio={task.get("ratio")}, resolution={task.get("resolution")}, '
                    f'duration={task.get("duration")}, prompt={task.get("prompt", "")[:50]}...')

        from openai import OpenAI

        client = OpenAI(api_key=task['api_key'], base_url=task['base_url'])

        logger.info(f'[{task_id}] 准备调用 Ark API: POST /contents/generations/tasks')

        resp = client.post(
            "/contents/generations/tasks",
            body={
                "model": task['model'],
                "content": [{"type": "text", "text": task.get('prompt', '')}],
                "ratio": task.get('ratio', '16:9'),
                "resolution": task.get('resolution', '720p'),
                "duration": task.get('duration', 8),
            },
            cast_to=object
        )

        remote_task_id = resp["id"]
        logger.info(f'[{task_id}] Ark 文生视频任务已创建: {remote_task_id}')

        redis_client.setex(f"task:{task_id}:remote_id", 3600, remote_task_id)
        redis_client.setex(f"task:{task_id}:api_key", 3600, task['api_key'])
        redis_client.setex(f"task:{task_id}:base_url", 3600, task['base_url'])
        redis_client.setex(f"task:{task_id}:provider", 3600, 'ark')
        redis_client.setex(f"task:{task_id}:user_id", 3600, str(task.get('user_id', '')))
        redis_client.setex(f"task:{task_id}:prompt", 3600, task.get('prompt', ''))
        redis_client.setex(f"task:{task_id}:model_id", 3600, str(task.get('model_id', '')))
        redis_client.setex(f"task:{task_id}:type", 3600, 'txt2video')
        redis_client.setex(f"task:{task_id}:history_id", 3600, str(task.get('history_id', '')))
        redis_client.setex(f"task:{task_id}:status", 3600, 'processing')
        logger.info(f'[{task_id}] Ark 文生视频已提交，等待轮询')

    except Exception as e:
        provider_error = parse_provider_error(e, 'ark')

        logger.error(
            f'[{task_id}] 提交 Ark 文生视频失败: {provider_error.message}',
            extra={'detail': provider_error.detail}
        )

        history_id = task.get('history_id')
        error_message = f"{provider_error.message} | {provider_error.detail}"

        try:
            if history_id:
                history_repo.update_history(history_id=history_id, output_asset_ids=[], status='error', message=error_message)
            else:
                history_repo.save_history(
                    task_id=task_id,
                    prompt=task.get('prompt', ''),
                    user_id=int(task['user_id']) if task.get('user_id') else 0,
                    model_id=int(task['model_id']) if task.get('model_id') else None,
                    input_asset_ids=[],
                    output_asset_ids=[],
                    status='error',
                    type_='txt2video',
                    mode='api',
                    message=error_message,
                )
        except Exception as db_err:
            logger.error(f'[{task_id}] 写入历史记录失败: {db_err}')
        redis_client.setex(f"task:{task_id}:status", 3600, 'failed')
        redis_client.setex(f"task:{task_id}:result", 3600, json.dumps({'error': {'error_message': error_message}, 'history_id': history_id}))


def process_img2video(task: dict) -> None:
    """提交图生视频任务到 Ark，保存 remote_id 等待轮询"""
    task_id = task['task_id']
    redis_client = _get_redis()

    try:
        redis_client.setex(f"task:{task_id}:status", 3600, 'processing')
        logger.info(f'[{task_id}] 正在处理 Ark 图生视频任务')

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
                    f'base_url={task.get("base_url")}, '
                    f'ratio={task.get("ratio")}, resolution={task.get("resolution")}, '
                    f'duration={task.get("duration")}, '
                    f'input_asset_ids={task.get("input_asset_ids", [])}, '
                    f'prompt={task.get("prompt", "")[:50]}...')

        from volcenginesdkarkruntime import Ark
        import oss2

        client = Ark(api_key=task['api_key'])

        # OSS 配置
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)

        all_media = []
        input_asset_ids = task.get('input_asset_ids', [])

        AUDIO_EXTS = {'mp3', 'wav', 'aac', 'ogg', 'flac', 'm4a', 'opus'}
        VIDEO_EXTS = {'mp4', 'mov', 'avi', 'webm'}

        if input_asset_ids:
            for asset_id in input_asset_ids:
                query = 'SELECT location FROM assets WHERE id = %s'
                result = execute_query(query, (asset_id,))
                if result:
                    location = result[0]['location']
                    file_path = pathlib.Path(location)
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                    ext = location.split('.')[-1].lower()
                    if ext in AUDIO_EXTS:
                        media_type = 'audio'
                    elif ext in VIDEO_EXTS:
                        media_type = 'video'
                    else:
                        media_type = 'image'
                    object_name = f"seedance/{int(time.time())}_{asset_id}.{ext}"
                    bucket.put_object(object_name, file_data)
                    file_url = f"https://{settings.OSS_BUCKET_NAME}.{settings.OSS_ENDPOINT.replace('https://', '')}/{object_name}"
                    logger.info(f'[{task_id}] 资产 {asset_id}({media_type}) 已上传至 OSS: {file_url}')
                    all_media.append({'url': file_url, 'media_type': media_type})

        logger.info(f'[{task_id}] 准备调用 Ark API: content_generation.tasks.create，media 数量={len(all_media)}')

        content = [{"type": "text", "text": task.get('prompt', '')}]
        for media in all_media:
            mt = media['media_type']
            if mt == 'video':
                content.append({"type": "video_url", "video_url": {"url": media['url']}, "role": "reference_video"})
            elif mt == 'audio':
                content.append({"type": "audio_url", "audio_url": {"url": media['url']}, "role": "reference_audio"})
            elif mt == 'image':
                content.append({"type": "image_url", "image_url": {"url": media['url']}, "role": "reference_image"})
            else:
                raise ValueError(f'不支持的资产类型: {mt}，asset url: {media["url"]}')

        resp = client.content_generation.tasks.create(
            model=task['model'],
            content=content,
            duration=task.get('duration', 8),
            ratio=task.get('ratio', '16:9'),
            resolution=task.get('resolution', '1080p'),
            watermark=False,
            generate_audio=True,
        )

        remote_task_id = resp.id
        logger.info(f'[{task_id}] Ark 图生视频任务已创建: {remote_task_id}')

        redis_client.setex(f"task:{task_id}:remote_id", 3600, remote_task_id)
        redis_client.setex(f"task:{task_id}:api_key", 3600, task['api_key'])
        redis_client.setex(f"task:{task_id}:base_url", 3600, task.get('base_url', ''))
        redis_client.setex(f"task:{task_id}:provider", 3600, 'ark')
        redis_client.setex(f"task:{task_id}:user_id", 3600, str(task.get('user_id', '')))
        redis_client.setex(f"task:{task_id}:prompt", 3600, task.get('prompt', ''))
        redis_client.setex(f"task:{task_id}:model_id", 3600, str(task.get('model_id', '')))
        redis_client.setex(f"task:{task_id}:input_asset_ids", 3600, json.dumps(task.get('input_asset_ids', [])))
        redis_client.setex(f"task:{task_id}:type", 3600, 'img2video')
        redis_client.setex(f"task:{task_id}:history_id", 3600, str(task.get('history_id', '')))
        redis_client.setex(f"task:{task_id}:status", 3600, 'processing')
        logger.info(f'[{task_id}] Ark 图生视频已提交，等待轮询')

    except Exception as e:
        provider_error = parse_provider_error(e, 'ark')

        logger.error(
            f'[{task_id}] 提交 Ark 图生视频失败: {provider_error.message}',
            extra={'detail': provider_error.detail}
        )

        history_id = task.get('history_id')
        error_message = f"{provider_error.message} | {provider_error.detail}"

        try:
            if history_id:
                history_repo.update_history(history_id=history_id, output_asset_ids=[], status='error', message=error_message)
            else:
                history_repo.save_history(
                    task_id=task_id,
                    prompt=task.get('prompt', ''),
                    user_id=int(task['user_id']) if task.get('user_id') else 0,
                    model_id=int(task['model_id']) if task.get('model_id') else None,
                    input_asset_ids=task.get('input_asset_ids', []),
                    output_asset_ids=[],
                    status='error',
                    type_='img2video',
                    mode='api',
                    message=error_message,
                )
        except Exception as db_err:
            logger.error(f'[{task_id}] 写入历史记录失败: {db_err}')
        redis_client.setex(f"task:{task_id}:status", 3600, 'failed')
        redis_client.setex(f"task:{task_id}:result", 3600, json.dumps({'error': {'error_message': error_message}, 'history_id': history_id}))
