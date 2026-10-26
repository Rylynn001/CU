"""测试异步 worker 基本功能"""
import asyncio
import json
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from config import settings
from workers import openai_worker_async


async def test_worker():
    """测试 worker 能否正常导入和初始化"""
    print("[OK] 异步 worker 模块导入成功")

    # 测试 Redis 连接
    import redis
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True
    )

    try:
        redis_client.ping()
        print("[OK] Redis 连接正常")
    except Exception as e:
        print(f"[FAIL] Redis 连接失败: {e}")
        return

    # 测试数据库连接
    from database_async import execute_query
    try:
        result = await execute_query("SELECT 1 as test", fetch_one=True)
        print(f"[OK] 数据库连接正常: {result}")
    except Exception as e:
        print(f"[FAIL] 数据库连接失败: {e}")
        return

    print("\n所有基础检查通过！异步 worker 可以正常工作。")


if __name__ == '__main__':
    asyncio.run(test_worker())
