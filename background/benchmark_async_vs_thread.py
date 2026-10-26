"""对比测试：协程 vs 线程性能"""
import asyncio
import threading
import time
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))


# 模拟 IO 密集型任务（图片生成 API 调用）
async def async_task(task_id: int):
    """模拟异步 API 调用"""
    await asyncio.sleep(0.5)  # 模拟 500ms API 延迟
    return f"Task-{task_id} completed"


def sync_task(task_id: int):
    """模拟同步 API 调用"""
    time.sleep(0.5)  # 模拟 500ms API 延迟
    return f"Task-{task_id} completed"


async def test_async_workers(num_tasks: int):
    """测试异步协程处理性能"""
    start = time.time()
    tasks = [async_task(i) for i in range(num_tasks)]
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start
    return elapsed, len(results)


def test_sync_workers(num_tasks: int, num_threads: int):
    """测试多线程处理性能"""
    results = []
    lock = threading.Lock()

    def worker():
        while True:
            with lock:
                if not task_queue:
                    break
                task_id = task_queue.pop(0)
            result = sync_task(task_id)
            with lock:
                results.append(result)

    task_queue = list(range(num_tasks))
    start = time.time()

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    elapsed = time.time() - start
    return elapsed, len(results)


def main():
    num_tasks = 20  # 模拟 20 个并发图片生成任务
    num_threads = 8  # 你当前的线程数

    print(f"测试场景：{num_tasks} 个并发任务（每个耗时 500ms）\n")

    # 测试协程
    print("=== 协程模式 ===")
    async_elapsed, async_count = asyncio.run(test_async_workers(num_tasks))
    print(f"完成任务数: {async_count}")
    print(f"总耗时: {async_elapsed:.2f}秒")
    print(f"平均吞吐: {async_count/async_elapsed:.2f} 任务/秒\n")

    # 测试线程
    print(f"=== 线程模式（{num_threads} 线程）===")
    sync_elapsed, sync_count = test_sync_workers(num_tasks, num_threads)
    print(f"完成任务数: {sync_count}")
    print(f"总耗时: {sync_elapsed:.2f}秒")
    print(f"平均吞吐: {sync_count/sync_elapsed:.2f} 任务/秒\n")

    # 对比
    speedup = sync_elapsed / async_elapsed
    print(f"=== 性能对比 ===")
    print(f"协程比线程快: {speedup:.2f}x")
    print(f"节省时间: {sync_elapsed - async_elapsed:.2f}秒 ({(1-1/speedup)*100:.1f}%)")


if __name__ == '__main__':
    main()
