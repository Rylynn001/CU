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
    """保存一条历史记录，返回新记录 id。输入输出资产均写入关联表"""
    import json as _json
    payload_json = _json.dumps(payload, ensure_ascii=False) if payload else None
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO history
               (task_id, prompt, mode, status, type, message, user_id, model_id, payload, del_flag)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)""",
            (task_id, prompt, mode, status, type_, message, user_id, model_id, payload_json)
        )
        history_id = cursor.lastrowid
        if output_asset_ids:
            cursor.executemany(
                "INSERT INTO history_assets_rel (history_id, asset_id) VALUES (%s, %s)",
                [(history_id, aid) for aid in output_asset_ids]
            )
        if input_asset_ids:
            cursor.executemany(
                "INSERT INTO history_input_assets_rel (history_id, asset_id) VALUES (%s, %s)",
                [(history_id, aid) for aid in input_asset_ids]
            )
        conn.commit()
        return history_id


def get_user_history(
    user_id: int,
    type_filter: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> tuple[list[dict], int]:
    """获取用户历史记录（分页），返回 (records, total)。一次 JOIN 查出所有关联资产"""
    offset = (page - 1) * page_size
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # 先查总数
        if type_filter:
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM history WHERE user_id = %s AND del_flag = 0 AND type LIKE %s",
                (user_id, f'%{type_filter}')
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM history WHERE user_id = %s AND del_flag = 0",
                (user_id,)
            )
        total = cursor.fetchone()['cnt']

        # 一次 JOIN 查出所有数据（history + 模型名 + 输出资产 + 输入资产）
        if type_filter:
            cursor.execute(
                """SELECT h.id, h.task_id, h.prompt, h.mode, h.status, h.type, h.message,
                          m.description AS model_name,
                          out_a.id AS out_asset_id, out_a.location AS out_location, out_a.asset_type AS out_type,
                          in_a.id AS in_asset_id, in_a.location AS in_location
                   FROM history h
                   LEFT JOIN api_models m ON h.model_id = m.id
                   LEFT JOIN history_assets_rel out_r ON h.id = out_r.history_id
                   LEFT JOIN assets out_a ON out_r.asset_id = out_a.id
                   LEFT JOIN history_input_assets_rel in_r ON h.id = in_r.history_id
                   LEFT JOIN input_assets in_a ON in_r.asset_id = in_a.id
                   WHERE h.user_id = %s AND h.del_flag = 0 AND h.type LIKE %s
                   ORDER BY h.id DESC, out_a.id, in_a.id
                   LIMIT %s OFFSET %s""",
                (user_id, f'%{type_filter}', page_size * 50, offset * 50)
                # LIMIT 放大倍数，避免 JOIN 展开后截断（后续 Python 聚合再截取真实 page_size）
            )
        else:
            cursor.execute(
                """SELECT h.id, h.task_id, h.prompt, h.mode, h.status, h.type, h.message,
                          m.description AS model_name,
                          out_a.id AS out_asset_id, out_a.location AS out_location, out_a.asset_type AS out_type,
                          in_a.id AS in_asset_id, in_a.location AS in_location
                   FROM history h
                   LEFT JOIN api_models m ON h.model_id = m.id
                   LEFT JOIN history_assets_rel out_r ON h.id = out_r.history_id
                   LEFT JOIN assets out_a ON out_r.asset_id = out_a.id
                   LEFT JOIN history_input_assets_rel in_r ON h.id = in_r.history_id
                   LEFT JOIN input_assets in_a ON in_r.asset_id = in_a.id
                   WHERE h.user_id = %s AND h.del_flag = 0
                   ORDER BY h.id DESC, out_a.id, in_a.id
                   LIMIT %s OFFSET %s""",
                (user_id, page_size * 50, offset * 50)
            )
        rows = cursor.fetchall()

    # Python 侧聚合：多行合并成一条 history 记录
    history_map = {}
    for row in rows:
        hid = row['id']
        if hid not in history_map:
            history_map[hid] = {
                'id': hid,
                'task_id': row['task_id'],
                'prompt': row['prompt'],
                'mode': row['mode'],
                'status': row['status'],
                'type': row['type'],
                'message': row['message'],
                'model_name': row.get('model_name') or '',
                'output_urls': [],
                'input_asset_ids': set(),
                'input_asset_urls': [],
            }

        # 聚合输出资产
        if row['out_asset_id']:
            out_id = row['out_asset_id']
            if not any(o['id'] == out_id for o in history_map[hid]['output_urls']):
                filename = _pathlib.Path(row['out_location']).name
                ext = _pathlib.Path(filename).suffix.lower()
                asset_type = 'video' if ext in ('.mp4', '.mov', '.avi', '.webm') else 'image'
                history_map[hid]['output_urls'].append({
                    'url': f'/api/api-proxy/output/{filename}',
                    'type': asset_type,
                    'id': out_id,
                })

        # 聚合输入资产
        if row['in_asset_id']:
            in_id = row['in_asset_id']
            history_map[hid]['input_asset_ids'].add(in_id)
            if not any(i['url'].endswith(_pathlib.Path(row['in_location']).name) for i in history_map[hid]['input_asset_urls']):
                filename = _pathlib.Path(row['in_location']).name
                ext = _pathlib.Path(filename).suffix.lower()
                asset_type = 'video' if ext in ('.mp4', '.mov', '.avi', '.webm') else 'image'
                history_map[hid]['input_asset_urls'].append({
                    'url': f'/api/api-proxy/input/{filename}',
                    'type': asset_type,
                })

    # 转为列表，转换 set → list，截取真实分页
    records = []
    for item in history_map.values():
        item['input_asset_ids'] = list(item['input_asset_ids'])
        records.append(item)
    records = records[:page_size]  # JOIN 展开导致多余行，这里截取回正确数量

    return records, total


def find_history_by_asset_id(user_id: int, asset_id: int) -> dict | None:
    """根据输出资产 id 反查所属的历史记录（通过 history_assets_rel 关联表查找）"""
    import json as _json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT h.id, h.task_id, h.prompt, h.mode, h.status, h.type, h.message, h.payload, h.model_id,
                      m.description AS model_name,
                      out_a.id AS out_asset_id, out_a.location AS out_location, out_a.asset_type AS out_type,
                      in_a.id AS in_asset_id, in_a.location AS in_location
               FROM history h
               LEFT JOIN api_models m ON h.model_id = m.id
               JOIN history_assets_rel target_r ON h.id = target_r.history_id
               LEFT JOIN history_assets_rel out_r ON h.id = out_r.history_id
               LEFT JOIN assets out_a ON out_r.asset_id = out_a.id
               LEFT JOIN history_input_assets_rel in_r ON h.id = in_r.history_id
               LEFT JOIN input_assets in_a ON in_r.asset_id = in_a.id
               WHERE h.user_id = %s AND h.del_flag = 0 AND target_r.asset_id = %s
               ORDER BY h.id DESC, out_a.id, in_a.id""",
            (user_id, asset_id)
        )
        rows = cursor.fetchall()
        if not rows:
            return None

        # 聚合第一条（ORDER BY DESC 已排序，取最新一条）
        first_id = rows[0]['id']
        payload_json = rows[0].get('payload')
        item = {
            'id': first_id,
            'task_id': rows[0]['task_id'],
            'prompt': rows[0]['prompt'],
            'mode': rows[0]['mode'],
            'status': rows[0]['status'],
            'type': rows[0]['type'],
            'message': rows[0]['message'],
            'model_name': rows[0].get('model_name') or '',
            'model_id': rows[0].get('model_id'),
            'payload': _json.loads(payload_json) if payload_json else None,
            'output_urls': [],
            'input_asset_ids': set(),
            'input_asset_urls': [],
        }

        for row in rows:
            if row['id'] != first_id:
                break  # 只取第一条 history
            if row['out_asset_id']:
                out_id = row['out_asset_id']
                if not any(o['id'] == out_id for o in item['output_urls']):
                    filename = _pathlib.Path(row['out_location']).name
                    ext = _pathlib.Path(filename).suffix.lower()
                    asset_type = 'video' if ext in ('.mp4', '.mov', '.avi', '.webm') else 'image'
                    item['output_urls'].append({
                        'url': f'/api/api-proxy/output/{filename}',
                        'type': asset_type,
                        'id': out_id,
                    })
            if row['in_asset_id']:
                in_id = row['in_asset_id']
                item['input_asset_ids'].add(in_id)
                if not any(i['url'].endswith(_pathlib.Path(row['in_location']).name) for i in item['input_asset_urls']):
                    filename = _pathlib.Path(row['in_location']).name
                    ext = _pathlib.Path(filename).suffix.lower()
                    asset_type = 'video' if ext in ('.mp4', '.mov', '.avi', '.webm') else 'image'
                    item['input_asset_urls'].append({
                        'url': f'/api/api-proxy/input/{filename}',
                        'type': asset_type,
                    })

        item['input_asset_ids'] = list(item['input_asset_ids'])
        return item


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
    """更新历史记录的状态和输出资产（先删旧关联，再插入新关联）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE history SET status = %s, message = %s WHERE id = %s",
            (status, message, history_id)
        )
        cursor.execute(
            "DELETE FROM history_assets_rel WHERE history_id = %s",
            (history_id,)
        )
        if output_asset_ids:
            cursor.executemany(
                "INSERT INTO history_assets_rel (history_id, asset_id) VALUES (%s, %s)",
                [(history_id, aid) for aid in output_asset_ids]
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
