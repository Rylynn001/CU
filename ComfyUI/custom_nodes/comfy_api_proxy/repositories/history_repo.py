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


def _build_history_item(row: dict) -> dict:
    """将 history 行数据组装成前端所需的完整结构（含关联资产 URL）"""
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
                        'id': aid,
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

    return item


def get_user_history(
    user_id: int,
    type_filter: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> tuple[list[dict], int]:
    """获取用户历史记录（分页），返回 (records, total)"""
    offset = (page - 1) * page_size
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if type_filter:
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM history WHERE user_id = %s AND del_flag = 0 AND type LIKE %s",
                (user_id, f'%{type_filter}')
            )
            total = cursor.fetchone()['cnt']
            cursor.execute(
                """SELECT h.id, h.task_id, h.prompt, h.mode, h.status, h.type, h.message,
                          h.input_file, h.output_file, m.description AS model_name
                   FROM history h LEFT JOIN api_models m ON h.model_id = m.id
                   WHERE h.user_id = %s AND h.del_flag = 0 AND h.type LIKE %s
                   ORDER BY h.id DESC LIMIT %s OFFSET %s""",
                (user_id, f'%{type_filter}', page_size, offset)
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM history WHERE user_id = %s AND del_flag = 0",
                (user_id,)
            )
            total = cursor.fetchone()['cnt']
            cursor.execute(
                """SELECT h.id, h.task_id, h.prompt, h.mode, h.status, h.type, h.message,
                          h.input_file, h.output_file, m.description AS model_name
                   FROM history h LEFT JOIN api_models m ON h.model_id = m.id
                   WHERE h.user_id = %s AND h.del_flag = 0
                   ORDER BY h.id DESC LIMIT %s OFFSET %s""",
                (user_id, page_size, offset)
            )
        rows = cursor.fetchall()

    return [_build_history_item(row) for row in rows], total


def find_history_by_asset_id(user_id: int, asset_id: int) -> dict | None:
    """根据输出资产 id 反查所属的历史记录（output_file 存的是逗号分隔的资产 id 列表）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT h.id, h.task_id, h.prompt, h.mode, h.status, h.type, h.message,
                      h.input_file, h.output_file, m.description AS model_name
               FROM history h LEFT JOIN api_models m ON h.model_id = m.id
               WHERE h.user_id = %s AND h.del_flag = 0
                 AND (h.output_file = %s
                      OR h.output_file LIKE %s
                      OR h.output_file LIKE %s
                      OR h.output_file LIKE %s)
               ORDER BY h.id DESC LIMIT 1""",
            (user_id, str(asset_id), f'{asset_id},%', f'%,{asset_id},%', f'%,{asset_id}')
        )
        row = cursor.fetchone()
        return _build_history_item(row) if row else None


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
