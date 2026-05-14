"""
Redis Worker - 处理异步图片生成任务
启动方式: python worker.py
"""
import redis
import json
import time
import logging
import pathlib
import sys
import os

# 添加父目录到 path，以便导入 config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_db_config, get_redis_config

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('worker')

OUTPUT_DIR = pathlib.Path(r'D:\AAAA\output')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Redis 连接
redis_client = redis.Redis(**get_redis_config())

def process_ark_txt2video_task(task):
    """处理火山引擎 Ark 文生视频任务 - 只提交任务，不轮询"""
    task_id = task['task_id']

    try:
        redis_client.set(f'task:{task_id}:status', 'processing')
        logger.info(f'[{task_id}] Processing Ark txt2video task')

        from openai import OpenAI

        # 初始化 OpenAI 兼容客户端
        client = OpenAI(api_key=task['api_key'], base_url=task['base_url'])

        # 创建视频生成任务
        resp = client.post(
            "/contents/generations/tasks",
            body={
                "model": task['model'],
                "content": [
                    {
                        "type": "text",
                        "text": task['prompt']
                    }
                ],
                "ratio": task.get('ratio', '16:9'),
                "resolution": task.get('resolution', '720p'),
                "duration": task.get('duration', 8)
            },
            cast_to=object
        )

        remote_task_id = resp["id"]
        logger.info(f'[{task_id}] Ark txt2video task created: {remote_task_id}')

        # 保存远程任务 ID 和相关信息到 Redis
        redis_client.setex(f'task:{task_id}:remote_id', 3600, remote_task_id)
        redis_client.setex(f'task:{task_id}:api_key', 3600, task['api_key'])
        redis_client.setex(f'task:{task_id}:base_url', 3600, task['base_url'])
        redis_client.setex(f'task:{task_id}:provider', 3600, 'ark')
        redis_client.setex(f'task:{task_id}:user_id', 3600, str(task.get('user_id', '')))

        # 更新状态为 processing
        redis_client.set(f'task:{task_id}:status', 'processing')
        logger.info(f'[{task_id}] Ark txt2video task submitted, waiting for polling')

    except Exception as e:
        logger.error(f'[{task_id}] Failed to submit Ark txt2video task: {e}')
        redis_client.set(f'task:{task_id}:status', 'failed')
        redis_client.setex(f'task:{task_id}:result', 3600, json.dumps({
            'error': {'error_message': str(e)}
        }))


def process_ark_img2video_task(task):
    """处理火山引擎 Ark 图生视频任务 - 只提交任务，不轮询"""
    task_id = task['task_id']

    try:
        redis_client.set(f'task:{task_id}:status', 'processing')
        logger.info(f'[{task_id}] Processing Ark img2video task')

        from volcenginesdkarkruntime import Ark
        import oss2
        import tempfile
        import pymysql

        # 初始化 Ark 客户端
        client = Ark(api_key=task['api_key'])

        # 初始化 OSS
        from config import get_oss_config
        oss_config = get_oss_config()
        auth = oss2.Auth(oss_config['access_key_id'], oss_config['access_key_secret'])
        bucket = oss2.Bucket(auth, oss_config['endpoint'], oss_config['bucket_name'])

        # 收集所有素材（保持顺序：先本地上传，后资产选择）
        all_media = []

        # 处理输入文件（上传到 OSS）
        input_files = task.get('input_files', [])
        for file_info in input_files:
            # 从 hex 恢复二进制数据
            file_data = bytes.fromhex(file_info['data'])
            filename = file_info['filename']
            content_type = file_info['content_type']

            # 判断文件类型
            ext = filename.split('.')[-1].lower()
            is_video = ext in ['mp4', 'mov', 'avi', 'webm']

            # 上传到 OSS
            import time
            object_name = f"seedance/{int(time.time())}_{filename}"
            bucket.put_object(object_name, file_data)
            file_url = f"https://{oss_config['bucket_name']}.{oss_config['endpoint'].replace('https://', '')}/{object_name}"

            logger.info(f'[{task_id}] Uploaded to OSS: {file_url}')

            all_media.append({
                'url': file_url,
                'is_video': is_video
            })

        # 处理输入资产（从数据库读取并上传到 OSS）
        input_asset_ids = task.get('input_asset_ids', [])
        if input_asset_ids:
            conn = pymysql.connect(**get_db_config())
            try:
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    for asset_id in input_asset_ids:
                        cursor.execute('SELECT location FROM assets WHERE id = %s', (asset_id,))
                        asset = cursor.fetchone()
                        if asset:
                            location = asset['location']
                            # 读取文件
                            with open(location, 'rb') as f:
                                file_data = f.read()

                            # 判断文件类型
                            ext = location.split('.')[-1].lower()
                            is_video = ext in ['mp4', 'mov', 'avi', 'webm']

                            # 上传到 OSS
                            import time
                            object_name = f"seedance/{int(time.time())}_{asset_id}.{ext}"
                            bucket.put_object(object_name, file_data)
                            file_url = f"https://{oss_config['bucket_name']}.{oss_config['endpoint'].replace('https://', '')}/{object_name}"

                            logger.info(f'[{task_id}] Uploaded asset {asset_id} to OSS: {file_url}')

                            all_media.append({
                                'url': file_url,
                                'is_video': is_video
                            })
            finally:
                conn.close()

        # 构建 content 数组（前端已经添加了素材标签，直接使用原始 prompt）
        content = [
            {
                "type": "text",
                "text": task['prompt']
            }
        ]

        # 添加所有素材到 content（按顺序）
        for media in all_media:
            if media['is_video']:
                content.append({
                    "type": "video_url",
                    "video_url": {"url": media['url']},
                    "role": "reference_video"
                })
            else:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": media['url']},
                    "role": "reference_image"
                })

        # 调用 Ark API 创建任务
        resp = client.content_generation.tasks.create(
            model=task['model'],
            content=content,
            duration=task.get('duration', 8),
            ratio=task.get('ratio', '16:9'),
            resolution=task.get('resolution', '1080p'),
            watermark=False,
            generate_audio=True
        )

        remote_task_id = resp.id
        logger.info(f'[{task_id}] Ark task created: {remote_task_id}')

        # 保存远程任务 ID 和相关信息到 Redis
        redis_client.setex(f'task:{task_id}:remote_id', 3600, remote_task_id)
        redis_client.setex(f'task:{task_id}:api_key', 3600, task['api_key'])
        redis_client.setex(f'task:{task_id}:provider', 3600, 'ark')
        redis_client.setex(f'task:{task_id}:user_id', 3600, str(task.get('user_id', '')))

        # 更新状态为 processing
        redis_client.set(f'task:{task_id}:status', 'processing')
        logger.info(f'[{task_id}] Ark task submitted, waiting for polling')

    except Exception as e:
        logger.error(f'[{task_id}] Failed to submit Ark task: {e}')
        redis_client.set(f'task:{task_id}:status', 'failed')
        redis_client.setex(f'task:{task_id}:result', 3600, json.dumps({
            'error': {'error_message': str(e)}
        }))


def process_openai_task(task):
    """处理 OpenAI 生成任务"""
    task_id = task['task_id']

    try:
        redis_client.set(f'task:{task_id}:status', 'processing')
        logger.info(f'[{task_id}] Processing OpenAI task')

        from openai import OpenAI
        import uuid
        import pymysql
        import requests
        import base64
        import io

        # 初始化 OpenAI 客户端
        client = OpenAI(api_key=task['api_key'], base_url=task['base_url'])

        # 调用 OpenAI API
        width = task.get('width') or 1024
        height = task.get('height') or 1024
        n = task.get('n', 1)
        image_b64_list = task.get('image_b64_list', [])

        for i in range(3):
            try:
                # 图生图模式
                if image_b64_list:
                    # 将 base64 转为文件对象，并设置正确的 MIME 类型
                    image_files = []
                    for idx, b64_str in enumerate(image_b64_list):
                        img_bytes = base64.b64decode(b64_str)
                        # 创建带有文件名的 BytesIO 对象，指定 MIME 类型
                        img_file = io.BytesIO(img_bytes)
                        img_file.name = f'image_{idx+1}.png'  # 设置文件名，帮助识别 MIME 类型
                        image_files.append(img_file)

                    # 构建带序号的 prompt
                    full_prompt = ""
                    for idx in range(len(image_b64_list)):
                        full_prompt += f"图{idx+1}："
                    full_prompt += task['prompt']

                    response = client.images.edit(
                        model=task['model'],
                        prompt=full_prompt,
                        image=image_files,
                        # size=f"{width}x{height}",
                        n=n,
                    )
                # 文生图模式
                else:
                    response = client.images.generate(
                        model=task['model'],
                        prompt=task['prompt'],
                        # size=f"{width}x{height}",
                        n=n,
                    )
                break  # 成功则跳出重试循环
            except Exception as e:
                logger.warning(f'[{task_id}] Attempt {i+1} failed: {e}')
                if i < 2:  # 前两次失败后重试
                    time.sleep(3)
                else:  # 第三次失败则抛出
                    raise

        # 保存图片（支持 URL 和 base64）
        images = []
        save_paths = []

        for img in response.data:
            img_data = None

            # 优先使用 b64_json
            if hasattr(img, 'b64_json') and img.b64_json:
                img_data = base64.b64decode(img.b64_json)
            # 回退到 URL 下载
            elif hasattr(img, 'url') and img.url:
                img_response = requests.get(img.url, timeout=30)
                if img_response.status_code == 200:
                    img_data = img_response.content

            if img_data:
                filename = f'{uuid.uuid4().hex}.png'
                save_path = OUTPUT_DIR / filename

                with open(save_path, 'wb') as f:
                    f.write(img_data)

                url = f'/api/api-proxy/output/{filename}'
                images.append({'url': url, 'type': 'image'})
                save_paths.append(save_path)

        # 写入 assets 表
        if images and save_paths:
            user_id = task.get('user_id')
            if user_id:
                try:
                    conn = pymysql.connect(**get_db_config())
                    with conn:
                        with conn.cursor() as cursor:
                            for save_path in save_paths:
                                cursor.execute(
                                    'INSERT INTO assets (location, rfid, asset_type, created_at) VALUES (%s, %s, %s, NOW())',
                                    (str(save_path), int(user_id), 'picture')
                                )
                        conn.commit()
                    logger.info(f'[{task_id}] Saved to assets table as picture')
                except Exception as db_e:
                    logger.error(f'[{task_id}] DB insert failed: {db_e}')

        if not images:
            raise Exception('No image generated')

        # 更新 Redis 状态
        redis_client.set(f'task:{task_id}:status', 'completed')
        redis_client.setex(f'task:{task_id}:result', 3600, json.dumps({'result': images}))

        logger.info(f'[{task_id}] Completed, {len(images)} image(s)')

    except Exception as e:
        logger.error(f'[{task_id}] Failed: {e}')
        redis_client.set(f'task:{task_id}:status', 'failed')
        redis_client.setex(f'task:{task_id}:result', 3600, json.dumps({
            'error': {'error_message': str(e)}
        }))


def process_gemini_task(task):
    """处理 Gemini 生成任务"""
    task_id = task['task_id']

    try:
        redis_client.set(f'task:{task_id}:status', 'processing')
        logger.info(f'[{task_id}] Processing Gemini task')

        from google import genai
        from google.genai import types as genai_types
        import base64
        import uuid
        import tempfile
        import shutil
        import pymysql

        # 初始化 Gemini 客户端
        client = genai.Client(
            vertexai=True,
            api_key=task['api_key'],
            http_options={'base_url': task['base_url']}
        )

        # 构建 contents
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

        # 调用 Gemini API
        response = client.models.generate_content(
            model=task['model'],
            contents=contents
        )

        # 提取并保存图片
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

                        url = f'/api/api-proxy/output/{filename}'
                        images.append({'url': url, 'type': 'image'})
                        save_paths.append(save_path)

        # 只取最后一张（避免返回输入图）
        result_images = images[-1:] if images else []

        # 只把最后一张写入 assets 表
        if result_images and save_paths:
            user_id = task.get('user_id')
            if user_id:
                try:
                    conn = pymysql.connect(**get_db_config())
                    with conn:
                        with conn.cursor() as cursor:
                            cursor.execute(
                                'INSERT INTO assets (location, rfid, asset_type, created_at) VALUES (%s, %s, %s, NOW())',
                                (str(save_paths[-1]), int(user_id), 'picture')
                            )
                        conn.commit()
                    logger.info(f'[{task_id}] Saved to assets table as picture')
                except Exception as db_e:
                    logger.error(f'[{task_id}] DB insert failed: {db_e}')

        if not result_images:
            raise Exception('No image generated')

        # 更新 Redis 状态
        redis_client.set(f'task:{task_id}:status', 'completed')
        redis_client.setex(f'task:{task_id}:result', 3600, json.dumps({'result': result_images}))

        logger.info(f'[{task_id}] Completed, {len(result_images)} image(s)')

    except Exception as e:
        logger.error(f'[{task_id}] Failed: {e}')
        redis_client.set(f'task:{task_id}:status', 'failed')
        redis_client.setex(f'task:{task_id}:result', 3600, json.dumps({
            'error': {'error_message': str(e)}
        }))

def worker_loop(worker_id: int):
    """单个 worker 线程的主循环"""
    logger.info(f'[Worker-{worker_id}] Started')

    while True:
        try:
            # 优先处理图片队列，然后处理视频队列，最后处理图生视频队列
            result = redis_client.brpop(['queue:txt2img', 'queue:txt2video', 'queue:img2video'], timeout=1)

            if result:
                queue_name, task_json = result
                task = json.loads(task_json)
                task_id = task.get('task_id', 'unknown')

                logger.info(f'[Worker-{worker_id}] Processing task {task_id} from {queue_name}')

                provider = task.get('provider', 'unknown')

                # 图片生成任务
                if queue_name == 'queue:txt2img':
                    if provider == 'gemini':
                        process_gemini_task(task)
                    elif provider == 'openai':
                        process_openai_task(task)
                    else:
                        logger.warning(f'[Worker-{worker_id}] Unknown provider: {provider}')

                # 视频生成任务
                elif queue_name == 'queue:txt2video':
                    if provider == 'ark':
                        process_ark_txt2video_task(task)
                    else:
                        logger.warning(f'[Worker-{worker_id}] Unknown video provider: {provider}')

                # 图生视频任务
                elif queue_name == 'queue:img2video':
                    if provider == 'ark':
                        process_ark_img2video_task(task)
                    else:
                        logger.warning(f'[Worker-{worker_id}] Unknown img2video provider: {provider}')

        except KeyboardInterrupt:
            logger.info(f'[Worker-{worker_id}] Stopped by user')
            break
        except Exception as e:
            logger.error(f'[Worker-{worker_id}] Error: {e}')
            time.sleep(1)


def main():
    import threading

    # 启动多个 worker 线程并发处理队列
    num_workers = 4  # 降低到 4 个以减少内存占用
    logger.info(f'Starting {num_workers} worker threads...')

    threads = []
    for i in range(num_workers):
        thread = threading.Thread(target=worker_loop, args=(i+1,), daemon=True, name=f'Worker-{i+1}')
        thread.start()
        threads.append(thread)

    logger.info(f'{num_workers} workers started, waiting for tasks...')

    # 主线程等待（保持进程运行）
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        logger.info('Main thread stopped by user')


if __name__ == '__main__':
    main()
