"""
Redis Worker - 处理异步任务队列
启动方式: python worker.py（或由 __init__.py 在后台线程启动）
"""
import json
import time
import logging
import threading

logger = logging.getLogger('worker')


def _get_redis():
    import redis
    try:
        from .config import get_redis_config
    except ImportError:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from config import get_redis_config
    return redis.Redis(**get_redis_config())


def _import_workers():
    """兼容包内调用和独立运行两种场景"""
    try:
        from .workers import openai_worker, gemini_worker, ark_worker
    except ImportError:
        from workers import openai_worker, gemini_worker, ark_worker
    return openai_worker, gemini_worker, ark_worker


def worker_loop(worker_id: int, redis_client) -> None:
    """单个 worker 线程主循环"""
    logger.info(f'[Worker-{worker_id}] 已启动')

    openai_worker, gemini_worker, ark_worker = _import_workers()

    while True:
        try:
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

            logger.info(f'[Worker-{worker_id}] 正在处理 {task_id}，来自队列 {queue_name}')

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
                else:
                    logger.warning(f'[Worker-{worker_id}] 未知视频提供商: {provider}')

            elif queue_name in (b'queue:img2video', 'queue:img2video'):
                if provider == 'ark':
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
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    redis_client = _get_redis()
    from .config import get_worker_count
    num_workers = get_worker_count()
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
