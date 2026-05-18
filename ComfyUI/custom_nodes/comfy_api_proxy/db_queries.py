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


# ── History 查询 ──────────────────────────────────────────────────────────

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
) -> int:
    """保存一条历史记录，返回新记录的 id"""
    input_file = ','.join(str(i) for i in input_asset_ids) if input_asset_ids else None
    output_file = ','.join(str(i) for i in output_asset_ids) if output_asset_ids else None
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO history
               (task_id, prompt, mode, status, type, message, input_file, output_file, user_id, model_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (task_id, prompt, mode, status, type_, message, input_file, output_file, user_id, model_id)
        )
        conn.commit()
        return cursor.lastrowid


def get_user_history(user_id: int) -> list[dict]:
    """获取用户历史记录，关联 assets 表返回可访问的 URL"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, task_id, prompt, mode, status, type, message, input_file, output_file
               FROM history WHERE user_id = %s ORDER BY id DESC""",
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
            'output_urls': [],
            'input_asset_ids': [],
        }

        # 解析 output_file 字段，查询 assets 表获取 location
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
                    assets = {a['id']: a for a in cursor.fetchall()}
                for aid in ids:
                    if aid in assets:
                        a = assets[aid]
                        import pathlib
                        filename = pathlib.Path(a['location']).name
                        item['output_urls'].append({
                            'url': f'/api/api-proxy/output/{filename}',
                            'type': a['asset_type'],
                        })

        # 解析 input_file 字段
        if row['input_file']:
            item['input_asset_ids'] = [int(x) for x in row['input_file'].split(',') if x.strip()]

        result.append(item)
    return result


def delete_history(history_id: int, user_id: int) -> bool:
    """删除单条历史记录（校验 user_id 防止越权）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM history WHERE id = %s AND user_id = %s",
            (history_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def clear_user_history(user_id: int) -> int:
    """清空用户所有历史记录，返回删除条数"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE user_id = %s", (user_id,))
        conn.commit()
        return cursor.rowcount
