"""历史记录数据库操作"""
import pathlib as _pathlib
from .database import get_db_connection


def save_history(
    user_id: int,
    prompt: str,
    input_asset_ids: list[int],
    output_asset_ids: list[int],
    task_id: str | None = None,
    mode: str | None = None,
    status: str = 'done',
    type_: str | None = None,
    message: str | None = None,
    model_id: int | None = None,
    payload: dict | None = None,
) -> int:
    """保存一条历史记录，返回新记录 id"""
    import json as _json
    input_file = ','.join(str(i) for i in input_asset_ids) if input_asset_ids else None
    output_file = ','.join(str(i) for i in output_asset_ids) if output_asset_ids else None
    payload_json = _json.dumps(payload, ensure_ascii=False) if payload else None
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO history
               (task_id, prompt, mode, status, type, message, input_file, output_file, user_id, model_id, payload, del_flag)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)""",
            (task_id, prompt, mode, status, type_, message, input_file, output_file, user_id, model_id, payload_json)
        )
        conn.commit()
        return cursor.lastrowid


def get_user_history(user_id: int, type_filter: str | None = None) -> list[dict]:
    """获取用户历史记录，关联 assets / input_assets 表返回可访问的 URL"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if type_filter:
            cursor.execute(
                """SELECT h.id, h.task_id, h.prompt, h.mode, h.status, h.type, h.message,
                          h.input_file, h.output_file, m.description AS model_name
                   FROM history h LEFT JOIN api_models m ON h.model_id = m.id
                   WHERE h.user_id = %s AND h.del_flag = 0 AND h.type LIKE %s ORDER BY h.id DESC""",
                (user_id, f'%{type_filter}')
            )
        else:
            cursor.execute(
                """SELECT h.id, h.task_id, h.prompt, h.mode, h.status, h.type, h.message,
                          h.input_file, h.output_file, m.description AS model_name
                   FROM history h LEFT JOIN api_models m ON h.model_id = m.id
                   WHERE h.user_id = %s AND h.del_flag = 0 ORDER BY h.id DESC""",
                (user_id,)
            )
        rows = cursor.fetchall()

    result = []
    for row in rows:
        item = {
            'id': row['id'],
            'task_id': row['task_id'],
            'prompt': row['prompt'],
            'mode': row['mode'],
            'status': row['status'],
            'type': row['type'],
            'message': row['message'],
            'model_name': row.get('model_name') or '',
            'output_urls': [],
            'input_asset_ids': [],
            'input_asset_urls': [],
        }

        if row['output_file']:
            ids = [int(x) for x in row['output_file'].split(',') if x.strip()]
            if ids:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    placeholders = ','.join(['%s'] * len(ids))
                    cursor.execute(
                        f"SELECT id, location, asset_type FROM assets WHERE id IN ({placeholders})",
                        ids
                    )
                    out_assets = {a['id']: a for a in cursor.fetchall()}
                for aid in ids:
                    if aid in out_assets:
                        filename = _pathlib.Path(out_assets[aid]['location']).name
                        ext = _pathlib.Path(filename).suffix.lower()
                        asset_type = 'video' if ext in ('.mp4', '.mov', '.avi', '.webm') else 'image'
                        item['output_urls'].append({
                            'url': f'/api/api-proxy/output/{filename}',
                            'type': asset_type,
                        })

        if row['input_file']:
            ids = [int(x) for x in row['input_file'].split(',') if x.strip()]
            item['input_asset_ids'] = ids
            if ids:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    placeholders = ','.join(['%s'] * len(ids))
                    cursor.execute(
                        f"SELECT id, location FROM input_assets WHERE id IN ({placeholders})",
                        ids
                    )
                    in_assets = {a['id']: a for a in cursor.fetchall()}
                for aid in ids:
                    if aid in in_assets:
                        filename = _pathlib.Path(in_assets[aid]['location']).name
                        ext = _pathlib.Path(filename).suffix.lower()
                        asset_type = 'video' if ext in ('.mp4', '.mov', '.avi', '.webm') else 'image'
                        item['input_asset_urls'].append({
                            'url': f'/api/api-proxy/input/{filename}',
                            'type': asset_type,
                        })

        result.append(item)
    return result


def get_history_by_id(history_id: int) -> dict | None:
    """根据 id 获取单条历史记录（未删除）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, task_id, prompt, type, payload, model_id, user_id FROM history WHERE id = %s AND del_flag = 0",
            (history_id,)
        )
        return cursor.fetchone()


def update_history(
    history_id: int,
    status: str,
    output_asset_ids: list[int],
    message: str | None = None,
) -> None:
    """更新历史记录的状态和输出资产"""
    output_file = ','.join(str(i) for i in output_asset_ids) if output_asset_ids else None
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE history SET status = %s, output_file = %s, message = %s WHERE id = %s",
            (status, output_file, message, history_id)
        )
        conn.commit()


def soft_delete_history(history_id: int) -> None:
    """软删除单条历史记录（不校验 user_id，供内部重试使用）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE history SET del_flag = 1 WHERE id = %s", (history_id,))
        conn.commit()


def delete_history(history_id: int, user_id: int) -> bool:
    """软删除单条历史记录"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE history SET del_flag = 1 WHERE id = %s AND user_id = %s AND del_flag = 0",
            (history_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def clear_user_history(user_id: int) -> int:
    """软删除用户所有历史记录，返回影响条数"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE history SET del_flag = 1 WHERE user_id = %s AND del_flag = 0", (user_id,))
        conn.commit()
        return cursor.rowcount
