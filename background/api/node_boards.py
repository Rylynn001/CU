"""工作区（Node Boards）相关路由"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import json

from api.auth import get_current_user
from database import execute_query

router = APIRouter()


class BoardCreate(BaseModel):
    name: str = "新工作区"


class BoardUpdate(BaseModel):
    name: str | None = None
    panel1_asset_ids: list[int] | None = None
    panel2_asset_ids: list[int] | None = None
    panel3_asset_ids: list[int] | None = None
    panel2_image_history_ids: list[int] | None = None
    panel2_video_history_ids: list[int] | None = None


@router.get("/node-boards")
async def list_node_boards(current_user: dict = Depends(get_current_user)):
    """获取用户的所有工作区"""
    user_id = current_user['user_id']

    boards = execute_query(
        '''SELECT id, name, updated_at
           FROM node_board
           WHERE user_id = %s AND deleted_at IS NULL
           ORDER BY updated_at DESC''',
        (user_id,),
        fetch_all=True
    ) or []

    # 转换时间戳为毫秒
    for b in boards:
        if b.get('updated_at'):
            b['updated_at'] = int(b['updated_at'].timestamp() * 1000)

    return {'boards': boards}


@router.post("/node-boards")
async def create_node_board(
    req: BoardCreate,
    current_user: dict = Depends(get_current_user)
):
    """创建新工作区"""
    user_id = current_user['user_id']
    name = req.name.strip() or '新工作区'

    board_id = execute_query(
        '''INSERT INTO node_board (user_id, name, created_at, updated_at)
           VALUES (%s, %s, NOW(), NOW())''',
        (user_id, name)
    )

    board = execute_query(
        'SELECT id, name, updated_at FROM node_board WHERE id = %s',
        (board_id,),
        fetch_one=True
    )

    if board and board.get('updated_at'):
        board['updated_at'] = int(board['updated_at'].timestamp() * 1000)

    return board


@router.get("/node-boards/{board_id}")
async def get_node_board(
    board_id: int,
    current_user: dict = Depends(get_current_user)
):
    """获取工作区详情（含三个面板数据）"""
    user_id = current_user['user_id']

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

    if not board:
        raise HTTPException(status_code=404, detail='工作区不存在')

    # 解析 JSON 字段
    for field in ['panel1_asset_ids', 'panel2_asset_ids', 'panel3_asset_ids',
                  'panel2_image_history_ids', 'panel2_video_history_ids']:
        value = board.get(field)
        if isinstance(value, str):
            try:
                board[field] = json.loads(value)
            except:
                board[field] = []
        elif value is None:
            board[field] = []

    # 加载面板数据
    board['panel1'] = _load_assets(board['panel1_asset_ids'])
    board['panel2'] = _load_assets(board['panel2_asset_ids'])
    board['panel3'] = _load_assets(board['panel3_asset_ids'])

    # 加载待处理任务
    board['panel2_image_tasks'] = _load_pending_tasks(board['panel2_image_history_ids'])
    board['panel2_video_tasks'] = _load_pending_tasks(board['panel2_video_history_ids'])

    if board.get('updated_at'):
        board['updated_at'] = int(board['updated_at'].timestamp() * 1000)

    return board


@router.put("/node-boards/{board_id}")
async def update_node_board(
    board_id: int,
    req: BoardUpdate,
    current_user: dict = Depends(get_current_user)
):
    """更新工作区"""
    user_id = current_user['user_id']

    # 检查权限
    board = execute_query(
        'SELECT id FROM node_board WHERE id = %s AND user_id = %s AND deleted_at IS NULL',
        (board_id, user_id),
        fetch_one=True
    )

    if not board:
        raise HTTPException(status_code=404, detail='工作区不存在')

    # 构建更新语句
    updates = []
    params = []

    if req.name is not None:
        updates.append('name = %s')
        params.append(req.name.strip() or '新工作区')

    if req.panel1_asset_ids is not None:
        updates.append('panel1_asset_ids = %s')
        params.append(json.dumps(req.panel1_asset_ids))

    if req.panel2_asset_ids is not None:
        updates.append('panel2_asset_ids = %s')
        params.append(json.dumps(req.panel2_asset_ids))

    if req.panel3_asset_ids is not None:
        updates.append('panel3_asset_ids = %s')
        params.append(json.dumps(req.panel3_asset_ids))

    if req.panel2_image_history_ids is not None:
        updates.append('panel2_image_history_ids = %s')
        params.append(json.dumps(req.panel2_image_history_ids))

    if req.panel2_video_history_ids is not None:
        updates.append('panel2_video_history_ids = %s')
        params.append(json.dumps(req.panel2_video_history_ids))

    if updates:
        updates.append('updated_at = NOW()')
        params.append(board_id)
        execute_query(
            f"UPDATE node_board SET {', '.join(updates)} WHERE id = %s",
            tuple(params)
        )

    return {'success': True}


@router.delete("/node-boards/{board_id}")
async def delete_node_board(
    board_id: int,
    current_user: dict = Depends(get_current_user)
):
    """删除工作区（软删除）"""
    user_id = current_user['user_id']

    execute_query(
        'UPDATE node_board SET deleted_at = NOW() WHERE id = %s AND user_id = %s',
        (board_id, user_id)
    )

    return {'success': True}


@router.patch("/node-boards/{board_id}")
async def rename_node_board(
    board_id: int,
    req: BoardCreate,
    current_user: dict = Depends(get_current_user)
):
    """重命名工作区（部分更新）"""
    user_id = current_user['user_id']
    name = req.name.strip() or '新工作区'

    execute_query(
        'UPDATE node_board SET name = %s, updated_at = NOW() WHERE id = %s AND user_id = %s',
        (name, board_id, user_id)
    )

    return {'success': True}


def _load_assets(asset_ids: list[int]) -> list[dict]:
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


def _load_pending_tasks(history_ids: list[int]) -> list[dict]:
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
