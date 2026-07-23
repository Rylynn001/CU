"""节点面板（board）数据库操作，软删除版本"""
import json
from datetime import datetime
from .database import get_db_connection


def list_boards(user_id: int) -> list[dict]:
    """获取用户所有未删除工作区，按更新时间倒序"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT id, name, updated_at
               FROM node_board
               WHERE user_id = %s AND deleted_at IS NULL
               ORDER BY updated_at DESC''',
            (user_id,)
        )
        rows = cursor.fetchall()
    for r in rows:
        if r.get('updated_at'):
            r['updated_at'] = int(r['updated_at'].timestamp() * 1000)
    return rows


def get_board(board_id: int, user_id: int) -> dict | None:
    """获取单个未删除工作区完整数据（含三个面板）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT id, name,
                      panel1_asset_ids, panel2_asset_ids, panel3_asset_ids,
                      panel1_ratio, panel2_ratio, panel3_ratio,
                      updated_at
               FROM node_board
               WHERE id = %s AND user_id = %s AND deleted_at IS NULL''',
            (board_id, user_id)
        )
        row = cursor.fetchone()
    if not row:
        return None
    for key in ('panel1_asset_ids', 'panel2_asset_ids', 'panel3_asset_ids'):
        if isinstance(row[key], str):
            row[key] = json.loads(row[key])
    if row.get('updated_at'):
        row['updated_at'] = int(row['updated_at'].timestamp() * 1000)
    return row


def create_board(user_id: int, name: str) -> dict:
    """新建工作区，返回 {id, name, updated_at}"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO node_board (user_id, name) VALUES (%s, %s)',
            (user_id, name)
        )
        conn.commit()
        board_id = cursor.lastrowid
    return {'id': board_id, 'name': name, 'updated_at': 0}


def save_board(board_id: int, user_id: int,
               panel1_ids: list, panel2_ids: list, panel3_ids: list,
               panel1_ratio: float, panel2_ratio: float, panel3_ratio: float) -> bool:
    """保存面板数据（仅操作未删除记录），返回是否成功"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''UPDATE node_board
               SET panel1_asset_ids = %s, panel2_asset_ids = %s, panel3_asset_ids = %s,
                   panel1_ratio = %s, panel2_ratio = %s, panel3_ratio = %s
               WHERE id = %s AND user_id = %s AND deleted_at IS NULL''',
            (
                json.dumps(panel1_ids), json.dumps(panel2_ids), json.dumps(panel3_ids),
                panel1_ratio, panel2_ratio, panel3_ratio,
                board_id, user_id,
            )
        )
        conn.commit()
        return cursor.rowcount > 0


def rename_board(board_id: int, user_id: int, name: str) -> bool:
    """重命名工作区（仅操作未删除记录）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''UPDATE node_board SET name = %s
               WHERE id = %s AND user_id = %s AND deleted_at IS NULL''',
            (name, board_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_board(board_id: int, user_id: int) -> bool:
    """软删除工作区（设置 deleted_at，不实际删除行）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''UPDATE node_board SET deleted_at = %s
               WHERE id = %s AND user_id = %s AND deleted_at IS NULL''',
            (datetime.now(), board_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
