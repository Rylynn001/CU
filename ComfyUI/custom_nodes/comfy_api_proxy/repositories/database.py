"""数据库连接"""
import pymysql
import logging
from ..config import get_db_config as _get_db_config

logger = logging.getLogger('comfy_api_proxy')


def get_db_connection():
    try:
        config = _get_db_config()
        config['cursorclass'] = pymysql.cursors.DictCursor
        return pymysql.connect(**config)
    except Exception as e:
        logger.error(f'[database] 连接失败: {e}')
        raise
