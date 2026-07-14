"""Provider 和 Model 数据库操作"""
from typing import Optional
from .database import get_db_connection


def get_all_providers() -> list[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_providers ORDER BY created_at DESC")
        return cursor.fetchall()


def get_provider_by_id(provider_id: int) -> Optional[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_providers WHERE id = %s", (provider_id,))
        return cursor.fetchone()


def get_default_provider() -> Optional[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_providers ORDER BY id ASC LIMIT 1")
        return cursor.fetchone()


def save_default_provider(base_url: str | None, encrypted_key: str | None) -> dict:
    provider = get_default_provider()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if provider:
            cursor.execute(
                'UPDATE api_providers SET url = COALESCE(%s, url), `key` = COALESCE(%s, `key`) WHERE id = %s',
                (base_url, encrypted_key, provider['id'])
            )
            provider_id = provider['id']
        else:
            if not base_url or not encrypted_key:
                raise ValueError('base_url and api_key are required for initial configuration')
            cursor.execute(
                'INSERT INTO api_providers (url, `key`) VALUES (%s, %s)',
                (base_url, encrypted_key)
            )
            provider_id = cursor.lastrowid
        conn.commit()
    return get_provider_by_id(provider_id)


def create_provider(name: str, base_url: str, api_key: str, is_default: bool = False,
                    is_active: bool = True, description: str = '') -> dict:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO api_providers (name, url, `key`, description) VALUES (%s, %s, %s, %s)",
            (name, base_url, api_key, description)
        )
        conn.commit()
        provider_id = cursor.lastrowid
    return get_provider_by_id(provider_id)


def get_all_models(provider_id: int | None = None) -> list[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if provider_id:
            cursor.execute("SELECT * FROM api_models WHERE rfid = %s ORDER BY id DESC", (provider_id,))
        else:
            cursor.execute("SELECT * FROM api_models ORDER BY id DESC")
        return cursor.fetchall()


def get_model_by_id(model_id: int) -> Optional[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_models WHERE id = %s", (model_id,))
        return cursor.fetchone()


def get_model_by_name(name: str, provider_id: int | None = None) -> Optional[dict]:
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


def get_model_by_model_id(model_id: str, provider_id: int) -> Optional[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM api_models WHERE name = %s AND rfid = %s LIMIT 1",
            (model_id, provider_id)
        )
        return cursor.fetchone()


def create_model(provider_id: int, model_id: str, name: str, description: str = None,
                 model_type: str = 'image', is_active: bool = True, sort_order: int = 0,
                 provider: str | None = None) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO api_models (rfid, name, description, type, provider) VALUES (%s, %s, %s, %s, %s)",
            (provider_id, model_id, description or name, model_type, provider)
        )
        conn.commit()


def delete_model(model_id: int) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM api_models WHERE id = %s", (model_id,))
        conn.commit()
