"""历史记录相关路由"""
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from api.auth import get_current_user
from repositories import history_repo

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
        asset = history_repo.find_asset_by_filename_and_user(filename, user_id)
        if asset:
            output_asset_ids.append(asset['id'])

    # 保存历史记录
    history_id = history_repo.save_history(
        user_id=user_id,
        prompt=req.prompt,
        input_asset_ids=req.input_asset_ids or [],
        output_asset_ids=output_asset_ids,
        task_id=req.task_id,
        mode=req.mode,
        status=req.status,
        type_=req.type,
        message=req.message,
        model_id=req.model_id,
        payload=None
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
    total = history_repo.count_history(user_id, type)

    # 查询记录（先分页再 JOIN 资产）
    rows = history_repo.list_history_with_assets(user_id, type, page_size, offset)

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
            filename = Path(row['out_location']).name if row['out_location'] else ''
            ext = Path(filename).suffix.lower()
            asset_type = 'video' if ext in ('.mp4', '.mov', '.avi', '.webm') else 'image'
            history_map[hid]['output_urls'].append({
                'url': f'/api/api-proxy/output/{filename}',
                'type': asset_type,
                'id': row['out_asset_id']
            })

        # 添加输入资产
        if row['in_asset_id']:
            history_map[hid]['input_asset_ids'].add(row['in_asset_id'])
            filename = Path(row['in_location']).name if row['in_location'] else ''
            if not any(i['url'].endswith(filename) for i in history_map[hid]['input_asset_urls']):
                ext = Path(filename).suffix.lower()
                asset_type = 'video' if ext in ('.mp4', '.mov', '.avi', '.webm') else 'image'
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
    rows = history_repo.get_history_by_asset(user_id, asset_id)

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
                filename = Path(row['out_location']).name if row['out_location'] else ''
                ext = Path(filename).suffix.lower()
                asset_type = 'video' if ext in ('.mp4', '.mov', '.avi', '.webm') else 'image'
                record['output_urls'].append({
                    'url': f'/api/api-proxy/output/{filename}',
                    'type': asset_type,
                    'id': out_id,
                })

        # 添加输入资产
        if row['in_asset_id']:
            in_id = row['in_asset_id']
            record['input_asset_ids'].add(in_id)
            filename = Path(row['in_location']).name if row['in_location'] else ''
            if not any(i['url'].endswith(filename) for i in record['input_asset_urls']):
                ext = Path(filename).suffix.lower()
                asset_type = 'video' if ext in ('.mp4', '.mov', '.avi', '.webm') else 'image'
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

    result = history_repo.delete_history(history_id, user_id)

    return {'ok': result > 0}


@router.delete("/history")
async def clear_history(current_user: dict = Depends(get_current_user)):
    """清空历史记录"""
    user_id = current_user['user_id']

    count = history_repo.clear_all_history(user_id)

    return {'deleted': count}


@router.post("/history/{history_id}/retry")
async def retry_history(
    history_id: int,
    current_user: dict = Depends(get_current_user)
):
    """重试失败的历史记录"""
    import json
    import uuid
    import base64
    import redis
    from pathlib import Path
    from config import settings
    from repositories import generation_repo

    user_id = current_user['user_id']

    row = history_repo.get_history_by_id(history_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail=f'history {history_id} not found')

    payload_raw = row.get('payload')
    if not payload_raw:
        raise HTTPException(status_code=400, detail='该记录没有保存 payload，无法重试')

    payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
    type_ = row.get('type', '')
    model_id = payload.get('model')
    prompt = payload.get('prompt', '')
    payload_user_id = payload.get('user_id')

    # Redis 客户端
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True
    )

    # 检查 Redis 可用性
    try:
        redis_client.ping()
    except:
        raise HTTPException(status_code=503, detail='Redis not available')

    provider_id = None
    from config import get_provider_config_by_rfid
    model_info = generation_repo.get_model_info(model_id)
    provider_config = get_provider_config_by_rfid(model_info['rfid'])
    api_key = provider_config['api_key']
    base_url = provider_config['base_url']
    model_name = model_info['name']

    new_task_id = str(uuid.uuid4())

    if type_ in ('txt2img', 'img2img'):
        queue_name = 'queue:txt2img'
        if redis_client.llen(queue_name) >= 100:
            raise HTTPException(status_code=503, detail='系统繁忙，请稍后再试')

        input_asset_ids = payload.get('input_asset_ids', [])

        # 加载参考图 base64
        image_b64_list = []
        if input_asset_ids:
            asset_map = generation_repo.load_input_assets(input_asset_ids)
            for asset_id in input_asset_ids:
                asset = asset_map.get(asset_id)
                if asset:
                    file_path = Path(asset['location'])
                    if file_path.exists():
                        image_b64_list.append(base64.b64encode(file_path.read_bytes()).decode())

        provider = model_info.get('provider', '')
        if not provider:
            raise HTTPException(status_code=400, detail=f'model {model_id} 未配置 provider 字段')

        new_history_id = history_repo.save_history(
            task_id=new_task_id,
            prompt=prompt,
            user_id=int(payload_user_id) if payload_user_id else 0,
            model_id=int(model_id) if model_id else None,
            input_asset_ids=input_asset_ids,
            output_asset_ids=[],
            status='pending',
            type_=type_,
            mode='api',
            payload=payload,
        )
        task_payload = {
            'task_id': new_task_id,
            'provider': provider,
            'model': model_name,
            'model_id': model_id,
            'prompt': prompt,
            'aspect_ratio': payload.get('aspect_ratio', '1:1'),
            'quality': payload.get('quality', 'medium'),
            'n': payload.get('n', 1),
            'user_id': payload_user_id,
            'api_key': api_key,
            'base_url': base_url,
            'image_b64_list': image_b64_list,
            'input_asset_ids': input_asset_ids,
            'history_id': new_history_id,
        }
        redis_client.lpush(queue_name, json.dumps(task_payload, ensure_ascii=False))

    elif type_ == 'txt2video':
        queue_name = 'queue:txt2video'
        if redis_client.llen(queue_name) >= 100:
            raise HTTPException(status_code=503, detail='系统繁忙，请稍后再试')

        new_history_id = history_repo.save_history(
            task_id=new_task_id,
            prompt=prompt,
            user_id=int(payload_user_id) if payload_user_id else 0,
            model_id=int(model_id) if model_id else None,
            input_asset_ids=[],
            output_asset_ids=[],
            status='pending',
            type_='txt2video',
            mode='api',
            payload=payload,
        )
        task_payload = {
            'task_id': new_task_id,
            'provider': 'ark',
            'model': model_name,
            'model_id': model_id,
            'prompt': prompt,
            'ratio': payload.get('ratio', '16:9'),
            'resolution': payload.get('resolution', '720p'),
            'duration': payload.get('duration', 8),
            'user_id': payload_user_id,
            'api_key': api_key,
            'base_url': base_url,
            'history_id': new_history_id,
        }
        redis_client.lpush(queue_name, json.dumps(task_payload, ensure_ascii=False))

    elif type_ == 'img2video':
        queue_name = 'queue:img2video'
        if redis_client.llen(queue_name) >= 100:
            raise HTTPException(status_code=503, detail='系统繁忙，请稍后再试')

        input_asset_ids = payload.get('input_asset_ids', [])
        new_history_id = history_repo.save_history(
            task_id=new_task_id,
            prompt=prompt,
            user_id=int(payload_user_id) if payload_user_id else 0,
            model_id=int(model_id) if model_id else None,
            input_asset_ids=input_asset_ids,
            output_asset_ids=[],
            status='pending',
            type_='img2video',
            mode='api',
            payload=payload,
        )
        task_payload = {
            'task_id': new_task_id,
            'provider': 'ark',
            'model': model_name,
            'model_id': model_id,
            'prompt': prompt,
            'ratio': payload.get('ratio', '16:9'),
            'resolution': payload.get('resolution', '720p'),
            'duration': int(payload.get('duration', 8)),
            'user_id': payload_user_id,
            'api_key': api_key,
            'base_url': base_url,
            'input_asset_ids': input_asset_ids,
            'history_id': new_history_id,
            'input_files': [],
        }
        redis_client.lpush(queue_name, json.dumps(task_payload, ensure_ascii=False))

    else:
        raise HTTPException(status_code=400, detail=f'不支持的任务类型: {type_}')

    redis_client.setex(f'task:{new_task_id}:status', 3600, 'pending')
    history_repo.soft_delete_history(history_id)

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f'[retry] history {history_id} → new task {new_task_id}, type={type_}')

    return {'task_id': new_task_id, 'history_id': new_history_id}
