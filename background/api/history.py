"""历史记录相关路由"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from api.auth import get_current_user
from database import execute_query

router = APIRouter()


class HistorySaveRequest(BaseModel):
    model_config = {'protected_namespaces': ()}

    prompt: str = ""
    output_urls: list[str] = []
    input_asset_ids: list[int] = []
    task_id: str | None = None
    mode: str | None = None
    status: str = "done"
    type: str | None = None
    message: str | None = None
    model_id: int | None = None


@router.post("/history")
async def save_history(
    req: HistorySaveRequest,
    current_user: dict = Depends(get_current_user)
):
    """保存历史记录"""
    user_id = current_user['user_id']

    # 从 URL 查找资产 ID
    output_asset_ids = []
    for url in req.output_urls:
        filename = url.split('/')[-1]
        asset = execute_query(
            'SELECT id FROM assets WHERE location LIKE %s AND rfid = %s LIMIT 1',
            (f'%{filename}', user_id),
            fetch_one=True
        )
        if asset:
            output_asset_ids.append(asset['id'])

    # 保存历史记录
    history_id = execute_query(
        '''INSERT INTO history (user_id, prompt, task_id, mode, status, type, message, model_id, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())''',
        (user_id, req.prompt, req.task_id, req.mode, req.status, req.type, req.message, req.model_id)
    )

    # 关联输入资产
    if req.input_asset_ids:
        for asset_id in req.input_asset_ids:
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

    return {'id': history_id}


@router.get("/history")
async def get_history(
    current_user: dict = Depends(get_current_user),
    type: str = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100)
):
    """获取历史记录（带输入输出资产）"""
    user_id = current_user['user_id']
    offset = (page - 1) * page_size

    where = "user_id = %s AND del_flag = 0"
    params = [user_id]

    if type:
        where += " AND type LIKE %s"
        params.append(f'%{type}')

    # 查询总数
    total = execute_query(
        f'SELECT COUNT(*) as cnt FROM history WHERE {where}',
        tuple(params),
        fetch_one=True
    )['cnt']

    # 查询记录（先分页再 JOIN 资产）
    rows = execute_query(
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

    # 聚合多行为单条记录
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
                'input_asset_urls': []
            }

        # 添加输出资产（转为 URL 格式）
        if row['out_asset_id'] and not any(o['id'] == row['out_asset_id'] for o in history_map[hid]['output_urls']):
            filename = row['out_location'].split('/')[-1] if row['out_location'] else ''
            ext = filename.split('.')[-1].lower() if '.' in filename else ''
            asset_type = 'video' if ext in ('mp4', 'mov', 'avi', 'webm') else 'image'
            history_map[hid]['output_urls'].append({
                'url': f'/api/api-proxy/output/{filename}',
                'type': asset_type,
                'id': row['out_asset_id']
            })

        # 添加输入资产
        if row['in_asset_id']:
            history_map[hid]['input_asset_ids'].add(row['in_asset_id'])
            filename = row['in_location'].split('/')[-1] if row['in_location'] else ''
            if not any(i['url'].endswith(filename) for i in history_map[hid]['input_asset_urls']):
                ext = filename.split('.')[-1].lower() if '.' in filename else ''
                asset_type = 'video' if ext in ('mp4', 'mov', 'avi', 'webm') else 'image'
                history_map[hid]['input_asset_urls'].append({
                    'url': f'/api/api-proxy/output/{filename}',
                    'type': asset_type
                })

    # 转为列表，input_asset_ids 从 set 转为 list
    records = []
    for item in history_map.values():
        item['input_asset_ids'] = list(item['input_asset_ids'])
        records.append(item)

    return {'records': records, 'total': total, 'page': page, 'page_size': page_size}


@router.get("/history/by-asset/{asset_id}")
async def get_history_by_asset(
    asset_id: int,
    current_user: dict = Depends(get_current_user)
):
    """根据资产查找历史记录（返回完整的输入输出资产）"""
    user_id = current_user['user_id']
    import json

    # 查询该资产关联的历史记录（包含输入输出资产）
    rows = execute_query(
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

    if not rows:
        raise HTTPException(status_code=404, detail='未找到该资产对应的历史记录')

    # 聚合第一条（已按 id DESC 排序，取最新一条）
    first_id = rows[0]['id']
    payload_json = rows[0].get('payload')
    record = {
        'id': first_id,
        'task_id': rows[0]['task_id'],
        'prompt': rows[0]['prompt'],
        'mode': rows[0]['mode'],
        'status': rows[0]['status'],
        'type': rows[0]['type'],
        'message': rows[0]['message'],
        'model_name': rows[0].get('model_name') or '',
        'model_id': rows[0].get('model_id'),
        'payload': json.loads(payload_json) if payload_json else None,
        'output_urls': [],
        'input_asset_ids': set(),
        'input_asset_urls': [],
    }

    # 聚合输出和输入资产
    for row in rows:
        if row['id'] != first_id:
            break  # 只取第一条 history

        # 添加输出资产
        if row['out_asset_id']:
            out_id = row['out_asset_id']
            if not any(o['id'] == out_id for o in record['output_urls']):
                filename = row['out_location'].split('/')[-1] if row['out_location'] else ''
                ext = filename.split('.')[-1].lower() if '.' in filename else ''
                asset_type = 'video' if ext in ('mp4', 'mov', 'avi', 'webm') else 'image'
                record['output_urls'].append({
                    'url': f'/api/api-proxy/output/{filename}',
                    'type': asset_type,
                    'id': out_id,
                })

        # 添加输入资产
        if row['in_asset_id']:
            in_id = row['in_asset_id']
            record['input_asset_ids'].add(in_id)
            filename = row['in_location'].split('/')[-1] if row['in_location'] else ''
            if not any(i['url'].endswith(filename) for i in record['input_asset_urls']):
                ext = filename.split('.')[-1].lower() if '.' in filename else ''
                asset_type = 'video' if ext in ('mp4', 'mov', 'avi', 'webm') else 'image'
                record['input_asset_urls'].append({
                    'url': f'/api/api-proxy/output/{filename}',
                    'type': asset_type,
                })

    record['input_asset_ids'] = list(record['input_asset_ids'])
    return {'record': record}


@router.delete("/history/{history_id}")
async def delete_history(
    history_id: int,
    current_user: dict = Depends(get_current_user)
):
    """删除历史记录"""
    user_id = current_user['user_id']

    result = execute_query(
        'DELETE FROM history WHERE id = %s AND user_id = %s',
        (history_id, user_id)
    )

    return {'ok': result > 0}


@router.delete("/history")
async def clear_history(current_user: dict = Depends(get_current_user)):
    """清空历史记录"""
    user_id = current_user['user_id']

    count = execute_query(
        'DELETE FROM history WHERE user_id = %s',
        (user_id,)
    )

    return {'deleted': count}


@router.post("/history/{history_id}/retry")
async def retry_history(
    history_id: int,
    current_user: dict = Depends(get_current_user)
):
    """重试失败的历史记录"""
    user_id = current_user['user_id']

    # 查询历史记录
    row = execute_query(
        'SELECT id, task_id, prompt, type, model_id, payload FROM history WHERE id = %s AND user_id = %s',
        (history_id, user_id),
        fetch_one=True
    )

    if not row:
        raise HTTPException(status_code=404, detail=f'history {history_id} not found')

    payload_raw = row.get('payload')
    if not payload_raw:
        raise HTTPException(status_code=400, detail='该记录没有保存 payload，无法重试')

    import json
    import uuid
    payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw

    # 生成新任务 ID
    new_task_id = str(uuid.uuid4())

    # 获取任务类型
    type_ = row.get('type', '')
    input_asset_ids = payload.get('input_asset_ids', [])

    # 创建新的历史记录
    new_history_id = execute_query(
        '''INSERT INTO history (user_id, task_id, prompt, mode, status, type, model_id, payload, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())''',
        (user_id, new_task_id, row['prompt'], 'api', 'pending', type_, row['model_id'], json.dumps(payload))
    )

    # 复制输入资产关联
    if input_asset_ids:
        for asset_id in input_asset_ids:
            execute_query(
                'INSERT INTO history_input_assets_rel (history_id, asset_id) VALUES (%s, %s)',
                (new_history_id, asset_id)
            )

    # 软删除旧记录
    execute_query(
        'UPDATE history SET del_flag = 1 WHERE id = %s',
        (history_id,)
    )

    return {'task_id': new_task_id, 'history_id': new_history_id}
