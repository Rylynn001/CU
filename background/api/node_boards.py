"""工作区（Node Boards）相关路由"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import json

from api.auth import get_current_user
from repositories import node_board_repo

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

    boards = node_board_repo.list_user_boards(user_id)

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

    board_id = node_board_repo.create_board(user_id, name)

    board = node_board_repo.get_board_by_id(board_id)

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

    board = node_board_repo.get_board_detail(board_id, user_id)

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
    board['panel1'] = node_board_repo.load_assets(board['panel1_asset_ids'])
    board['panel2'] = node_board_repo.load_assets(board['panel2_asset_ids'])
    board['panel3'] = node_board_repo.load_assets(board['panel3_asset_ids'])

    # 加载待处理任务
    board['panel2_image_tasks'] = node_board_repo.load_pending_tasks(board['panel2_image_history_ids'])
    board['panel2_video_tasks'] = node_board_repo.load_pending_tasks(board['panel2_video_history_ids'])

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
    board = node_board_repo.check_board_permission(board_id, user_id)

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
        node_board_repo.update_board(board_id, updates, params)

    return {'success': True}


@router.delete("/node-boards/{board_id}")
async def delete_node_board(
    board_id: int,
    current_user: dict = Depends(get_current_user)
):
    """删除工作区（软删除）"""
    user_id = current_user['user_id']

    node_board_repo.delete_board(board_id, user_id)

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

    node_board_repo.rename_board(board_id, user_id, name)

    return {'success': True}

