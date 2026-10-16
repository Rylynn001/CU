"""加密解密工具（1:1 从 ComfyUI 复制）"""
from cryptography.fernet import Fernet
from config import settings


def encrypt(key: bytes, plaintext: str) -> str:
    return Fernet(key).encrypt(plaintext.encode()).decode()


def decrypt(key: bytes, token: str) -> str:
    return Fernet(key).decrypt(token.encode()).decode()


def decrypt_api_key(token: str) -> str:
    """用 .env 中的 ENCRYPTION_KEY 解密数据库里存的 api_key"""
    key = settings.ENCRYPTION_KEY
    if not key:
        raise RuntimeError("ENCRYPTION_KEY 未配置")
    return decrypt(key.encode(), token)
