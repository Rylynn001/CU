"""异步数据库连接管理"""
import logging
import aiomysql
from contextlib import asynccontextmanager

from config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_db():
    """异步数据库连接上下文管理器"""
    conn = None
    try:
        conn = await aiomysql.connect(
            host=settings.DB_HOST,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            db=settings.DB_NAME,
            charset='utf8mb4',
            cursorclass=aiomysql.DictCursor
        )
        yield conn
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        if conn:
            await conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


async def execute_query(query: str, params: tuple = None, fetch_one: bool = False, fetch_all: bool = False):
    """执行异步查询

    - fetch_one=True: 返回单行字典
    - fetch_all=True: 返回列表[字典]
    - 否则(写操作): 返回 lastrowid(INSERT) 或 rowcount(UPDATE/DELETE)
    """
    async with get_db() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(query, params or ())
            if fetch_one:
                return await cursor.fetchone()
            elif fetch_all:
                return await cursor.fetchall()
            else:
                await conn.commit()
                return cursor.lastrowid if cursor.lastrowid else cursor.rowcount


async def execute_many(query: str, params_list: list):
    """批量执行"""
    async with get_db() as conn:
        async with conn.cursor() as cursor:
            await cursor.executemany(query, params_list)
            await conn.commit()
            return cursor.rowcount
