"""资产相关数据库操作"""
from .database import get_db_connection


def save_output_asset(location: str, user_id: int, asset_type: str) -> int:
    """写入 assets 表，返回新记录 id"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO assets (location, rfid, asset_type, created_at) VALUES (%s, %s, %s, NOW())',
            (location, user_id, asset_type)
        )
        conn.commit()
        return cursor.lastrowid


def save_input_asset(user_id: int, filename: str, location: str) -> int:
    """写入 input_assets 表，返回新记录 id"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO input_assets (rfid, filename, location) VALUES (%s, %s, %s)',
            (user_id, filename, location)
        )
        conn.commit()
        return cursor.lastrowid


def get_input_asset(asset_id: int) -> dict | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM input_assets WHERE id = %s', (asset_id,))
        return cursor.fetchone()


def get_input_assets_by_ids(asset_ids: list[int]) -> list[dict]:
    if not asset_ids:
        return []
    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join(['%s'] * len(asset_ids))
        cursor.execute(
            f'SELECT id, location FROM input_assets WHERE id IN ({placeholders})',
            asset_ids
        )
        return cursor.fetchall()


def get_user_assets(user_id: int, asset_type: str | None = None) -> list[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if asset_type in ('picture', 'video'):
            cursor.execute(
                'SELECT id, location, asset_type FROM assets WHERE rfid = %s AND asset_type = %s ORDER BY id DESC',
                (user_id, asset_type)
            )
        else:
            cursor.execute(
                'SELECT id, location, asset_type FROM assets WHERE rfid = %s ORDER BY id DESC',
                (user_id,)
            )
        return cursor.fetchall()


def find_asset_by_filename(filename: str, user_id: int) -> dict | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM assets WHERE location LIKE %s AND rfid = %s ORDER BY id DESC LIMIT 1",
            (f'%{filename}', user_id)
        )
        return cursor.fetchone()
