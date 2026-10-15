"""配置管理"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""

    # 数据库配置
    DB_HOST: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_NAME: str = ""

    # Redis 配置
    REDIS_HOST: str = ""
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # JWT 配置
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    TOKEN_EXPIRE_DAYS: int = 3

    # 文件存储
    OUTPUT_DIR: Path = Path("output")
    INPUT_DIR: Path = Path("input")
    VOICE_DIR: Path = Path("voice")

    # OSS 配置
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET_NAME: str = ""
    OSS_ENDPOINT: str = ""

    # MiniMax 配置
    MINIMAX_API_KEY: str = ""
    MINIMAX_BASE_URL: str = "https://api.vectorengine.ai/minimax/v1"

    # Qwen 配置
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = ""
    QWEN_MODEL: str = "qwen-plus"

    # 加密密钥
    ENCRYPTION_KEY: str = ""

    # Worker 配置
    WORKER_COUNT: int = 4
    QUEUE_MAX_SIZE: int = 20

    class Config:
        # 使用绝对路径，确保从任何目录启动都能找到 .env 文件
        env_file = Path(__file__).parent / ".env"
        case_sensitive = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 确保目录存在
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.INPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.VOICE_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


def get_provider_config_by_rfid(rfid: int) -> dict | None:
    """根据 rfid 获取 provider 配置（包含解密后的 key）"""
    import logging
    logger = logging.getLogger(__name__)
    try:
        from repositories.provider_repo import get_provider_by_id
        logger.info(f"正在查询 provider, rfid={rfid}")
        provider = get_provider_by_id(rfid)
        logger.info(f"查询结果: {provider}")
        if provider:
            return {
                'id': provider['id'],
                'base_url': provider['url'],
                'api_key': provider['key'],  # 已解密
            }
    except Exception as e:
        logger.error(f"获取 provider 配置失败: {e}", exc_info=True)
        raise
    return None


settings = get_settings()
