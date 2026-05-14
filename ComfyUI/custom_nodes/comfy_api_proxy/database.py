"""数据库连接配置"""
import pymysql
import logging
import os
from . import config as cfg

logger = logging.getLogger('comfy_api_proxy')

# 从 config 模块获取数据库配置
def get_db_config():
    """获取数据库配置（从 .env 或环境变量）"""
    base_config = cfg.get_db_config()
    base_config['cursorclass'] = pymysql.cursors.DictCursor
    return base_config


def get_db_connection():
    """获取数据库连接"""
    try:
        conn = pymysql.connect(**get_db_config())
        return conn
    except Exception as e:
        logger.error(f'[database] Failed to connect: {e}')
        raise



# def init_database():
#     """初始化数据库表结构"""
#     conn = get_connection()
#     try:
#         with conn.cursor() as cursor:
#             # 创建 providers 表
#             cursor.execute("""
#                 CREATE TABLE IF NOT EXISTS providers (
#                     id VARCHAR(36) PRIMARY KEY,
#                     name VARCHAR(255) NOT NULL,
#                     base_url VARCHAR(512) NOT NULL,
#                     api_key VARCHAR(512) NOT NULL,
#                     is_default BOOLEAN DEFAULT FALSE,
#                     is_active BOOLEAN DEFAULT TRUE,
#                     description TEXT,
#                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#                     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
#                 )
#             """)
#
#             # 创建 models 表
#             cursor.execute("""
#                 CREATE TABLE IF NOT EXISTS models (
#                     id INT AUTO_INCREMENT PRIMARY KEY,
#                     provider_id VARCHAR(36) NOT NULL,
#                     model_id VARCHAR(255) NOT NULL,
#                     name VARCHAR(255) NOT NULL,
#                     description TEXT,
#                     model_type VARCHAR(50) DEFAULT 'image',
#                     is_active BOOLEAN DEFAULT TRUE,
#                     sort_order INT DEFAULT 0,
#                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#                     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
#                     FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
#                     UNIQUE KEY uk_provider_model (provider_id, model_id)
#                 )
#             """)
#
#             # 创建 sys_user 表（如果不存在）
#             cursor.execute("""
#                 CREATE TABLE IF NOT EXISTS sys_user (
#                     id INT AUTO_INCREMENT PRIMARY KEY,
#                     user_name VARCHAR(255) NOT NULL UNIQUE,
#                     password VARCHAR(255) NOT NULL,
#                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#                 )
#             """)
#
#             # 创建 assets 表（如果不存在）
#             cursor.execute("""
#                 CREATE TABLE IF NOT EXISTS assets (
#                     id INT AUTO_INCREMENT PRIMARY KEY,
#                     location VARCHAR(512) NOT NULL,
#                     rfid INT NOT NULL,
#                     asset_type VARCHAR(50) DEFAULT 'picture',
#                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#                 )
#             """)
#
#             # 创建 input_assets 表（如果不存在）
#             cursor.execute("""
#                 CREATE TABLE IF NOT EXISTS input_assets (
#                     id INT AUTO_INCREMENT PRIMARY KEY,
#                     rfid INT NOT NULL,
#                     filename VARCHAR(255) NOT NULL,
#                     location VARCHAR(512) NOT NULL,
#                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#                 )
#             """)
#
#             conn.commit()
#             logger.info('[database] Database tables initialized successfully')
#     except Exception as e:
#         logger.error(f'[database] Failed to initialize tables: {e}')
#         raise
#     finally:
#         conn.close()


# if __name__ == '__main__':
#     logging.basicConfig(level=logging.INFO)
#     # init_database()
#     print('Database initialized successfully')
