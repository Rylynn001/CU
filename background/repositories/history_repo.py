"""历史记录数据库操作"""
import json
import logging
from database import execute_query

logger = logging.getLogger('background')


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
    payload_json = json.dumps(payload, ensure_ascii=False) if payload else None

    history_id = execute_query(
        """INSERT INTO history
           (task_id, prompt, mode, status, type, message, user_id, model_id, payload, del_flag)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)""",
        (task_id, prompt, mode, status, type_, message, user_id, model_id, payload_json)
    )

    if output_asset_ids:
        for aid in output_asset_ids:
            execute_query(
                "INSERT INTO history_assets_rel (history_id, asset_id) VALUES (%s, %s)",
                (history_id, aid)
            )

    if input_asset_ids:
        for aid in input_asset_ids:
            execute_query(
                "INSERT INTO history_input_assets_rel (history_id, asset_id) VALUES (%s, %s)",
                (history_id, aid)
            )

    return history_id


def update_history(
    history_id: int,
    status: str,
    output_asset_ids: list[int],
    message: str | None = None,
) -> None:
    """更新历史记录的状态和输出资产（先删旧关联，再插入新关联）"""
    execute_query(
        "UPDATE history SET status = %s, message = %s WHERE id = %s",
        (status, message, history_id)
    )

    execute_query(
        "DELETE FROM history_assets_rel WHERE history_id = %s",
        (history_id,)
    )

    if output_asset_ids:
        for aid in output_asset_ids:
            execute_query(
                "INSERT INTO history_assets_rel (history_id, asset_id) VALUES (%s, %s)",
                (history_id, aid)
            )
