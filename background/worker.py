"""
Redis Worker - 处理异步任务队列
启动方式: python worker.py
"""
import json
import time
import logging
import threading
import sys
import pathlib

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from config import settings
from workers import openai_worker, gemini_worker, ark_worker

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def _get_redis():
    """获取 Redis 客户端"""
    import redis
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=False  # 接收字节以兼容队列名判断
    )


def worker_loop(worker_id: int, redis_client) -> None:
    """单个 worker 线程主循环。

    ``generation.py`` 只负责把任务放入 Redis；真正调用 OpenAI/Gemini 的地方在
    ``workers/openai_worker.py`` 和 ``workers/gemini_worker.py``。本函数负责取任务并分发。
    """
    logger.info(f'[Worker-{worker_id}] 已启动')

    while True:
        try:
            # =====【worker 取任务】=====
            # brpop 会阻塞等待 API 提交的 queue:txt2img 任务。
            result = redis_client.brpop(
                ['queue:txt2img', 'queue:txt2video', 'queue:img2video'],
                timeout=1
            )
            if not result:
                continue

            queue_name, task_json = result
            task = json.loads(task_json)
            task_id = task.get('task_id', 'unknown')
            provider = task.get('provider', 'unknown')

            logger.info(f'[Worker-{worker_id}] 拿到任务: task_id={task_id}, queue={queue_name}, provider={provider}')
            logger.info(f'[Worker-{worker_id}] 任务完整数据: {json.dumps(task, ensure_ascii=False)[:200]}...')

            # =====【按提供商分发图片任务】=====
            # 同一个 txt2img 队列，根据 provider 进入不同的图片 worker。
            if queue_name == b'queue:txt2img' or queue_name == 'queue:txt2img':
                if provider == 'gemini':
                    gemini_worker.process(task)
                elif provider == 'openai':
                    openai_worker.process(task)
                else:
                    logger.warning(f'[Worker-{worker_id}] 未知提供商: {provider}')

            elif queue_name in (b'queue:txt2video', 'queue:txt2video'):
                if provider == 'ark':
                    ark_worker.process_txt2video(task)
                elif provider == 'openai':
                    # Seedance 等 OpenAI 兼容的视频模型，复用 ark_worker
                    ark_worker.process_txt2video(task)
                else:
                    logger.warning(f'[Worker-{worker_id}] 未知视频提供商: {provider}')

            elif queue_name in (b'queue:img2video', 'queue:img2video'):
                if provider == 'ark':
                    ark_worker.process_img2video(task)
                elif provider == 'openai':
                    # Seedance 等 OpenAI 兼容的视频模型，复用 ark_worker
                    ark_worker.process_img2video(task)
                else:
                    logger.warning(f'[Worker-{worker_id}] 未知图生视频提供商: {provider}')

        except KeyboardInterrupt:
            logger.info(f'[Worker-{worker_id}] 已被用户停止')
            break
        except Exception as e:
            logger.error(f'[Worker-{worker_id}] 错误: {e}')
            time.sleep(1)


def main():
    redis_client = _get_redis()
    num_workers = settings.WORKER_COUNT
    logger.info(f'正在启动 {num_workers} 个 worker 线程...')

    threads = []
    for i in range(num_workers):
        t = threading.Thread(
            target=worker_loop,
            args=(i + 1, redis_client),
            daemon=True,
            name=f'Worker-{i+1}',
        )
        t.start()
        threads.append(t)

    logger.info(f'{num_workers} 个 worker 已启动，等待任务...')
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        logger.info('主线程已被用户停止')


if __name__ == '__main__':
    main()
