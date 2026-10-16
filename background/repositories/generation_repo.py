"""图片和视频生成相关的数据库操作"""
import json
from typing import List
from database import execute_query


def load_input_assets(input_asset_ids: List[int]):
    """批量读取参考图信息"""
    if not input_asset_ids:
        return []

    placeholders = ','.join(['%s'] * len(input_asset_ids))
    assets = execute_query(
        f"SELECT id, location FROM assets WHERE id IN ({placeholders})",
        tuple(input_asset_ids),
        fetch_all=True
    ) or []

    asset_map = {a['id']: a for a in assets}
    return asset_map


def get_model_info(model_id: int):
    """获取模型信息"""
    model_info = execute_query(
        "SELECT id, name, provider, rfid FROM api_models WHERE id = %s",
        (model_id,),
        fetch_one=True
    )
    return model_info


def save_history(
    task_id: str,
    prompt: str,
    user_id: int,
    model_id: int,
    input_asset_ids: List[int],
    output_asset_ids: List[int],
    status: str,
    type_: str,
    mode: str,
    payload: dict
):
    """保存历史记录"""
    history_id = execute_query(
        """
        INSERT INTO history
        (task_id, prompt, user_id, model_id, status, type, mode, payload, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (task_id, prompt, user_id, model_id, status, type_, mode, json.dumps(payload, ensure_ascii=False))
    )

    # 关联输入资产
    if input_asset_ids:
        for asset_id in input_asset_ids:
            execute_query(
                'INSERT INTO history_input_assets_rel (history_id, asset_id) VALUES (%s, %s)',
                (history_id, asset_id)
            )

    # 关联输出资产
    if output_asset_ids:
        for asset_id in output_asset_ids:
            execute_query(
                'INSERT INTO history_assets_rel (history_id, asset_id) VALUES (%s, %s)',
                (history_id, asset_id)
            )

    return history_id
