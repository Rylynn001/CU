"""历史记录异步数据库操作"""
import json
from typing import List, Optional
from database_worker import execute_query


async def find_asset_by_filename_and_user(filename: str, user_id: int):
    """根据文件名和用户ID查找资产"""
    asset = await execute_query(
        'SELECT id FROM assets WHERE location LIKE %s AND rfid = %s LIMIT 1',
        (f'%{filename}', user_id),
        fetch_one=True
    )
    return asset


async def save_history(
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
    payload_json = json.dumps(payload, ensure_ascii=False) if payload else None
    history_id = await execute_query(
        """INSERT INTO history
           (task_id, prompt, mode, status, type, message, user_id, model_id, payload, del_flag)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)""",
        (task_id, prompt, mode, status, type_, message, user_id, model_id, payload_json)
    )
    if output_asset_ids:
        for aid in output_asset_ids:
            await execute_query(
                "INSERT INTO history_assets_rel (history_id, asset_id) VALUES (%s, %s)",
                (history_id, aid)
            )
    if input_asset_ids:
        for aid in input_asset_ids:
            await execute_query(
                "INSERT INTO history_input_assets_rel (history_id, asset_id) VALUES (%s, %s)",
                (history_id, aid)
            )
    return history_id


async def link_input_asset(history_id: int, asset_id: int):
    """关联输入资产"""
    await execute_query(
        'INSERT INTO history_input_assets_rel (history_id, asset_id) VALUES (%s, %s)',
        (history_id, asset_id)
    )


async def link_output_asset(history_id: int, asset_id: int):
    """关联输出资产"""
    await execute_query(
        'INSERT INTO history_assets_rel (history_id, asset_id) VALUES (%s, %s)',
        (history_id, asset_id)
    )


async def count_history(user_id: int, type_filter: Optional[str] = None):
    """统计历史记录总数"""
    where = "user_id = %s AND del_flag = 0"
    params = [user_id]

    if type_filter:
        where += " AND type LIKE %s"
        params.append(f'%{type_filter}')

    result = await execute_query(
        f'SELECT COUNT(*) as cnt FROM history WHERE {where}',
        tuple(params),
        fetch_one=True
    )
    return result['cnt']


async def list_history_with_assets(user_id: int, type_filter: Optional[str], page_size: int, offset: int):
    """查询历史记录（包含输入输出资产）"""
    where = "user_id = %s AND del_flag = 0"
    params = [user_id]

    if type_filter:
        where += " AND type LIKE %s"
        params.append(f'%{type_filter}')

    rows = await execute_query(
        f"""SELECT h.id, h.task_id, h.prompt, h.mode, h.status, h.type, h.message, h.created_at,
                   m.description AS model_name,
                   out_a.id AS out_asset_id, out_a.location AS out_location, out_a.asset_type AS out_type,
                   in_a.id AS in_asset_id, in_a.location AS in_location
            FROM (SELECT id FROM history WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s) AS paged
            JOIN history h ON h.id = paged.id
            LEFT JOIN api_models m ON h.model_id = m.id
            LEFT JOIN history_assets_rel out_r ON h.id = out_r.history_id
            LEFT JOIN assets out_a ON out_r.asset_id = out_a.id
            LEFT JOIN history_input_assets_rel in_r ON h.id = in_r.history_id
            LEFT JOIN assets in_a ON in_r.asset_id = in_a.id
            ORDER BY h.id DESC, out_a.id, in_a.id""",
        tuple(params + [page_size, offset]),
        fetch_all=True
    ) or []
    return rows


async def get_history_by_asset(user_id: int, asset_id: int):
    """根据资产查找历史记录（包含输入输出资产）"""
    rows = await execute_query(
        """SELECT h.id, h.task_id, h.prompt, h.mode, h.status, h.type, h.message, h.payload, h.model_id,
                  m.description AS model_name,
                  out_a.id AS out_asset_id, out_a.location AS out_location, out_a.asset_type AS out_type,
                  in_a.id AS in_asset_id, in_a.location AS in_location
           FROM history h
           JOIN history_assets_rel target_r ON h.id = target_r.history_id
           LEFT JOIN api_models m ON h.model_id = m.id
           LEFT JOIN history_assets_rel out_r ON h.id = out_r.history_id
           LEFT JOIN assets out_a ON out_r.asset_id = out_a.id
           LEFT JOIN history_input_assets_rel in_r ON h.id = in_r.history_id
           LEFT JOIN assets in_a ON in_r.asset_id = in_a.id
           WHERE h.user_id = %s AND h.del_flag = 0 AND target_r.asset_id = %s
           ORDER BY h.id DESC, out_a.id, in_a.id""",
        (user_id, asset_id),
        fetch_all=True
    )
    return rows


async def delete_history(history_id: int, user_id: int):
    """删除历史记录"""
    result = await execute_query(
        'DELETE FROM history WHERE id = %s AND user_id = %s',
        (history_id, user_id)
    )
    return result


async def clear_all_history(user_id: int):
    """清空用户所有历史记录"""
    count = await execute_query(
        'DELETE FROM history WHERE user_id = %s',
        (user_id,)
    )
    return count


async def get_history_by_id(history_id: int, user_id: int):
    """根据ID查询历史记录"""
    row = await execute_query(
        'SELECT id, task_id, prompt, type, model_id, payload FROM history WHERE id = %s AND user_id = %s',
        (history_id, user_id),
        fetch_one=True
    )
    return row


async def update_history(
    history_id: int,
    status: str,
    output_asset_ids: list,
    message: Optional[str] = None,
):
    """更新历史记录的状态和输出资产（先删旧关联，再插入新关联）"""
    await execute_query(
        "UPDATE history SET status = %s, message = %s WHERE id = %s",
        (status, message, history_id)
    )
    await execute_query(
        "DELETE FROM history_assets_rel WHERE history_id = %s",
        (history_id,)
    )
    if output_asset_ids:
        for aid in output_asset_ids:
            await execute_query(
                "INSERT INTO history_assets_rel (history_id, asset_id) VALUES (%s, %s)",
                (history_id, aid)
            )


async def soft_delete_history(history_id: int):
    """软删除历史记录"""
    await execute_query(
        'UPDATE history SET del_flag = 1 WHERE id = %s',
        (history_id,)
    )
