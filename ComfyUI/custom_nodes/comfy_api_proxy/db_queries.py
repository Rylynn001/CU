"""数据库查询函数"""
from typing import Optional
from .database import get_db_connection


# ── API Provider 查询 ──────────────────────────────────────────────────────

def get_all_providers() -> list[dict]:
    """获取所有API提供商"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_providers ORDER BY created_at DESC")
        return cursor.fetchall()


def get_provider_by_id(provider_id: int) -> Optional[dict]:
    """根据ID获取提供商"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_providers WHERE id = %s", (provider_id,))
        return cursor.fetchone()


def get_default_provider() -> Optional[dict]:
    """获取默认提供商（返回第一个）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_providers ORDER BY id ASC LIMIT 1")
        return cursor.fetchone()


# ── API Model 查询 ────────────────────────────────────────────────────────

def get_all_models(provider_id: int | None = None) -> list[dict]:
    """获取所有模型"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if provider_id:
            cursor.execute("SELECT * FROM api_models WHERE rfid = %s ORDER BY id DESC", (provider_id,))
        else:
            cursor.execute("SELECT * FROM api_models ORDER BY id DESC")
        return cursor.fetchall()


def get_model_by_id(model_id: int) -> Optional[dict]:
    """根据ID获取模型"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_models WHERE id = %s", (model_id,))
        return cursor.fetchone()


def get_model_by_name(name: str, provider_id: int | None = None) -> Optional[dict]:
    """根据name获取模型（可选指定provider）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if provider_id:
            cursor.execute(
                "SELECT * FROM api_models WHERE name = %s AND rfid = %s LIMIT 1",
                (name, provider_id)
            )
        else:
            cursor.execute("SELECT * FROM api_models WHERE name = %s LIMIT 1", (name,))
        return cursor.fetchone()
