"""数据库连接管理"""
import logging
from contextlib import contextmanager
import pymysql
from pymysql.cursors import DictCursor

from config import settings

logger = logging.getLogger(__name__)


@contextmanager
def get_db():
    """数据库连接上下文管理器"""
    conn = None
    try:
        conn = pymysql.connect(
            host=settings.DB_HOST,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            charset='utf8mb4',
            cursorclass=DictCursor
        )
        yield conn
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def execute_query(query: str, params: tuple = None, fetch_one: bool = False, fetch_all: bool = False):
    """执行查询"""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            if fetch_one:
                return cursor.fetchone()
            elif fetch_all:
                return cursor.fetchall()
            else:
                conn.commit()
                return cursor.lastrowid


def execute_many(query: str, params_list: list):
    """批量执行"""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount
