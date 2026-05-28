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


def get_user_assets(user_id: int, asset_type: str | None = None, tag: int | None = None) -> list[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        sql = 'SELECT id, location, asset_type, tag FROM assets WHERE rfid = %s'
        params: list = [user_id]
        if asset_type in ('picture', 'video'):
            sql += ' AND asset_type = %s'
            params.append(asset_type)
        if tag is not None:
            sql += ' AND tag = %s'
            params.append(tag)
        sql += ' ORDER BY id DESC'
        cursor.execute(sql, params)
        return cursor.fetchall()


def set_asset_tag(asset_id: int, user_id: int, tag: int) -> bool:
    """设置资产 tag（1=收藏，0=取消收藏），返回是否成功"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE assets SET tag = %s WHERE id = %s AND rfid = %s',
            (tag, asset_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def get_asset_by_id(asset_id: int) -> dict | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, location, rfid, asset_type FROM assets WHERE id = %s', (asset_id,))
        return cursor.fetchone()


def find_asset_by_filename(filename: str, user_id: int) -> dict | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM assets WHERE location LIKE %s AND rfid = %s ORDER BY id DESC LIMIT 1",
            (f'%{filename}', user_id)
        )
        return cursor.fetchone()
