"""工作区（Node Boards）相关的数据库操作"""
import json
from database import execute_query


def list_user_boards(user_id: int):
    """获取用户的所有工作区"""
    boards = execute_query(
        '''SELECT id, name, updated_at
           FROM node_board
           WHERE user_id = %s AND deleted_at IS NULL
           ORDER BY updated_at DESC''',
        (user_id,),
        fetch_all=True
    ) or []
    return boards


def create_board(user_id: int, name: str):
    """创建新工作区"""
    board_id = execute_query(
        '''INSERT INTO node_board (user_id, name, created_at, updated_at)
           VALUES (%s, %s, NOW(), NOW())''',
        (user_id, name)
    )
    return board_id


def get_board_by_id(board_id: int):
    """获取工作区基本信息"""
    board = execute_query(
        'SELECT id, name, updated_at FROM node_board WHERE id = %s',
        (board_id,),
        fetch_one=True
    )
    return board


def get_board_detail(board_id: int, user_id: int):
    """获取工作区详情（含三个面板数据）"""
    board = execute_query(
        '''SELECT id, name,
                  panel1_asset_ids, panel2_asset_ids, panel3_asset_ids,
                  panel2_image_history_ids, panel2_video_history_ids,
                  updated_at
           FROM node_board
           WHERE id = %s AND user_id = %s AND deleted_at IS NULL''',
        (board_id, user_id),
        fetch_one=True
    )
    return board


def check_board_permission(board_id: int, user_id: int):
    """检查工作区权限"""
    board = execute_query(
        'SELECT id FROM node_board WHERE id = %s AND user_id = %s AND deleted_at IS NULL',
        (board_id, user_id),
        fetch_one=True
    )
    return board


def update_board(board_id: int, updates: list[str], params: list):
    """更新工作区"""
    if updates:
        updates.append('updated_at = NOW()')
        params.append(board_id)
        execute_query(
            f"UPDATE node_board SET {', '.join(updates)} WHERE id = %s",
            tuple(params)
        )


def delete_board(board_id: int, user_id: int):
    """删除工作区（软删除）"""
    execute_query(
        'UPDATE node_board SET deleted_at = NOW() WHERE id = %s AND user_id = %s',
        (board_id, user_id)
    )


def rename_board(board_id: int, user_id: int, name: str):
    """重命名工作区"""
    execute_query(
        'UPDATE node_board SET name = %s, updated_at = NOW() WHERE id = %s AND user_id = %s',
        (name, board_id, user_id)
    )


def load_assets(asset_ids: list[int]):
    """加载资产列表"""
    if not asset_ids:
        return []

    placeholders = ','.join(['%s'] * len(asset_ids))
    assets = execute_query(
        f'SELECT id, location, asset_type, tag FROM assets WHERE id IN ({placeholders})',
        tuple(asset_ids),
        fetch_all=True
    ) or []

    # 按原始顺序排序
    asset_map = {a['id']: a for a in assets}
    return [asset_map[aid] for aid in asset_ids if aid in asset_map]


def load_pending_tasks(history_ids: list[int]):
    """加载待处理任务"""
    if not history_ids:
        return []

    placeholders = ','.join(['%s'] * len(history_ids))
    rows = execute_query(
        f'''SELECT h.id, h.task_id, h.status, h.message, h.prompt, h.payload,
                   input_rel.asset_id
            FROM history h
            LEFT JOIN history_input_assets_rel input_rel ON input_rel.history_id = h.id
            WHERE h.id IN ({placeholders}) AND h.del_flag = 0
            ORDER BY h.id, input_rel.asset_id''',
        tuple(history_ids),
        fetch_all=True
    ) or []

    tasks = {}
    for item in rows:
        history_id = item['id']
        if history_id not in tasks:
            try:
                payload = json.loads(item['payload']) if item['payload'] else {}
            except:
                payload = {}
            tasks[history_id] = {
                'history_id': history_id,
                'task_id': item['task_id'],
                'status': item['status'],
                'message': item['message'],
                'prompt': item['prompt'] or '',
                'payload': payload,
                'input_asset_ids': []
            }
        if item['asset_id'] is not None:
            tasks[history_id]['input_asset_ids'].append(item['asset_id'])

    return [tasks[hid] for hid in history_ids if hid in tasks]
