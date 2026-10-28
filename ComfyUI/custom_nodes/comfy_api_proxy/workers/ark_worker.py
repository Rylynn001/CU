"""Ark (火山引擎) 视频生成 worker - 只提交任务，不轮询"""
import json
import time
import logging
from .. import config as cfg
from ..repositories import history_repo
from ..services import task_queue

logger = logging.getLogger('comfy_api_proxy')


def process_txt2video(task: dict) -> None:
    """提交文生/图生视频任务到 Ark，保存 remote_id 等待轮询"""
    task_id = task['task_id']
    try:
        task_queue.set_status(task_id, 'processing')
        input_asset_ids = task.get('input_asset_ids', [])

        if input_asset_ids:
            logger.info(f'[{task_id}] 正在处理 Ark 图生视频任务 (含 {len(input_asset_ids)} 个资产)')
        else:
            logger.info(f'[{task_id}] 正在处理 Ark 文生视频任务')

        from volcenginesdkarkruntime import Ark
        import oss2
        import pymysql
        from ..config import get_oss_config, get_db_config

        client = Ark(api_key=task['api_key'])

        # 准备 content
        content = [{"type": "text", "text": task['prompt']}]

        # 如果有 input_asset_ids,上传资产到 OSS 并添加到 content
        if input_asset_ids:
            oss_config = get_oss_config()
            auth = oss2.Auth(oss_config['access_key_id'], oss_config['access_key_secret'])
            bucket = oss2.Bucket(auth, oss_config['endpoint'], oss_config['bucket_name'])

            AUDIO_EXTS = {'mp3', 'wav', 'aac', 'ogg', 'flac', 'm4a', 'opus'}
            VIDEO_EXTS = {'mp4', 'mov', 'avi', 'webm'}

            conn = pymysql.connect(**get_db_config())
            try:
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    for asset_id in input_asset_ids:
                        cursor.execute('SELECT location FROM assets WHERE id = %s', (asset_id,))
                        asset = cursor.fetchone()
                        if asset:
                            location = asset['location']
                            with open(location, 'rb') as f:
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
                            file_url = f"https://{oss_config['bucket_name']}.{oss_config['endpoint'].replace('https://', '')}/{object_name}"
                            logger.info(f'[{task_id}] 资产 {asset_id}({media_type}) 已上传至 OSS: {file_url}')

                            # 添加到 content
                            if media_type == 'video':
                                content.append({"type": "video_url", "video_url": {"url": file_url}, "role": "reference_video"})
                            elif media_type == 'audio':
                                content.append({"type": "audio_url", "audio_url": {"url": file_url}, "role": "reference_audio"})
                            elif media_type == 'image':
                                content.append({"type": "image_url", "image_url": {"url": file_url}, "role": "reference_image"})
            finally:
                conn.close()

        # 调用 Ark API
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
        logger.info(f'[{task_id}] Ark 视频任务已创建: {remote_task_id}')

        task_queue.set_meta(task_id, 'remote_id', remote_task_id)
        task_queue.set_meta(task_id, 'api_key', task['api_key'])
        task_queue.set_meta(task_id, 'base_url', task.get('base_url', ''))
        task_queue.set_meta(task_id, 'provider', 'ark')
        task_queue.set_meta(task_id, 'user_id', str(task.get('user_id', '')))
        task_queue.set_meta(task_id, 'prompt', task.get('prompt', ''))
        task_queue.set_meta(task_id, 'model_id', str(task.get('model_id', '')))
        if input_asset_ids:
            task_queue.set_meta(task_id, 'input_asset_ids', json.dumps(input_asset_ids))
        task_queue.set_meta(task_id, 'type', 'txt2video')
        task_queue.set_meta(task_id, 'history_id', str(task.get('history_id', '')))
        task_queue.set_status(task_id, 'processing')
        logger.info(f'[{task_id}] Ark 视频任务已提交，等待轮询')

    except Exception as e:
        logger.error(f'[{task_id}] 提交 Ark 视频任务失败: {e}')
        history_id = task.get('history_id')
        error_message = str(e)
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
                    type_='txt2video',
                    mode='api',
                    message=error_message,
                )
        except Exception as db_err:
            logger.error(f'[{task_id}] 写入历史记录失败: {db_err}')
        task_queue.set_status(task_id, 'failed')
        task_queue.set_result(task_id, {'error': {'error_message': error_message}, 'history_id': history_id})

