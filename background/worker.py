"""
Redis Worker - 异步处理任务队列
启动方式: python worker.py
"""
import json
import logging
import asyncio
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from config import settings
from workers import openai_worker, gemini_worker, ark_worker
from agents.services.plan_scheduler import plan_scheduler_loop
from api.tasks import video_task_polling_loop

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def _get_redis_sync():
    """获取同步 Redis 客户端（用于 brpop）"""
    import redis
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=False
    )


async def worker_loop(worker_id: int) -> None:
    """单个 worker 协程主循环"""
    logger.info(f'[Worker-{worker_id}] 已启动')
    redis_client = _get_redis_sync()

    while True:
        try:
            # brpop 仍用同步（Redis 阻塞操作无法完全异步化）
            # 用 asyncio.to_thread 避免阻塞事件循环
            result = await asyncio.to_thread(
                redis_client.brpop,
                ['queue:txt2img', 'queue:txt2video'],
                1
            )
            if not result:
                continue

            queue_name, task_json = result
            task = json.loads(task_json)
            task_id = task.get('task_id', 'unknown')
            provider = task.get('provider', 'unknown')

            logger.info(f'[Worker-{worker_id}] 拿到任务: task_id={task_id}, queue={queue_name}, provider={provider}')

            handlers = {
                (b'queue:txt2img', 'gemini'): gemini_worker.process,
                (b'queue:txt2img', 'openai'): openai_worker.process,
                (b'queue:txt2video', 'ark'): ark_worker.process_txt2video,
                (b'queue:txt2video', 'openai'): ark_worker.process_txt2video,
            }
            handler = handlers.get((queue_name, provider))
            if handler:
                await handler(task)
            else:
                logger.warning('[Worker-%s] 不支持的生成队列或供应商: %s %s', worker_id, queue_name, provider)

        except asyncio.CancelledError:
            logger.info(f'[Worker-{worker_id}] 协程被取消')
            break
        except Exception as e:
            logger.error(f'[Worker-{worker_id}] 错误: {e}', exc_info=True)
            await asyncio.sleep(1)


async def main():
    num_workers = settings.WORKER_COUNT
    logger.info(f'正在启动 {num_workers} 个异步 worker...')

    tasks = [asyncio.create_task(worker_loop(i + 1)) for i in range(num_workers)]
    tasks.append(asyncio.create_task(plan_scheduler_loop()))
    tasks.append(asyncio.create_task(video_task_polling_loop()))

    logger.info(f'{num_workers} 个异步 worker 已启动，等待任务...')
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info('收到停止信号，正在关闭...')
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == '__main__':
    asyncio.run(main())
