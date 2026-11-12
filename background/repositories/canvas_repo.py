"""画布只保存文档 JSON，资产和生成任务沿用现有表。"""
import json
from database import execute_query


def list_canvases(user_id: int):
    return execute_query(
        'SELECT id, name, updated_at FROM canvas WHERE user_id = %s AND deleted_at IS NULL ORDER BY updated_at DESC, id DESC',
        (user_id,), fetch_all=True,
    ) or []


def get_canvas(canvas_id: int, user_id: int):
    return execute_query(
        'SELECT id, name, document, updated_at FROM canvas WHERE id = %s AND user_id = %s AND deleted_at IS NULL',
        (canvas_id, user_id), fetch_one=True,
    )


def create_canvas(user_id: int, name: str, document: dict):
    return execute_query(
        'INSERT INTO canvas (user_id, name, document) VALUES (%s, %s, %s)',
        (user_id, name, json.dumps(document, ensure_ascii=False)),
    )


def save_canvas(canvas_id: int, user_id: int, name: str, document: dict):
    execute_query(
        'UPDATE canvas SET name = %s, document = %s, updated_at = CURRENT_TIMESTAMP(3) WHERE id = %s AND user_id = %s AND deleted_at IS NULL',
        (name, json.dumps(document, ensure_ascii=False), canvas_id, user_id),
    )


def delete_canvas(canvas_id: int, user_id: int):
    execute_query(
        'UPDATE canvas SET deleted_at = CURRENT_TIMESTAMP(3) WHERE id = %s AND user_id = %s AND deleted_at IS NULL',
        (canvas_id, user_id),
    )


def get_history_task(history_id: int, user_id: int):
    """Redis 状态过期后，仍可从数据库恢复生成结果。"""
    rows = execute_query(
        '''SELECT h.id, h.task_id, h.status, h.message, rel.asset_id
           FROM history h LEFT JOIN history_assets_rel rel ON rel.history_id = h.id
           WHERE h.id = %s AND h.user_id = %s AND h.del_flag = 0
           ORDER BY rel.asset_id''',
        (history_id, user_id), fetch_all=True,
    ) or []
    if not rows:
        return None
    return {
        'history_id': rows[0]['id'], 'task_id': rows[0]['task_id'],
        'status': rows[0]['status'], 'message': rows[0]['message'],
        'asset_ids': [row['asset_id'] for row in rows if row['asset_id'] is not None],
    }
