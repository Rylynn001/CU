"""图片和视频生成接口（从 ComfyUI 迁移）"""
import uuid
import json
import base64
import logging
import redis
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

from repositories import generation_repo
from config import settings
from .auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

# Redis 客户端
_redis_client = None

def get_redis():
    """获取 Redis 客户端"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
    return _redis_client

def enqueue_task(queue_name: str, task_data: dict) -> None:
    """任务入队"""
    client = get_redis()
    client.lpush(queue_name, json.dumps(task_data, ensure_ascii=False))
    # 设置任务状态
    task_id = task_data['task_id']
    client.setex(f'task:{task_id}:status', 3600, 'pending')


class Txt2ImgRequest(BaseModel):
    """文生图请求"""
    model: int
    prompt: str
    aspect_ratio: str = "1:1"
    quality: str = "medium"
    n: int = 1
    input_asset_ids: Optional[List[int]] = None


class Txt2VideoRequest(BaseModel):
    """文生视频请求"""
    model: int
    prompt: str
    ratio: str = "16:9"
    resolution: str = "720p"
    duration: int = 8


class Img2VideoRequest(BaseModel):
    """图生视频请求"""
    model: int
    prompt: str
    ratio: str = "16:9"
    resolution: str = "720p"
    duration: int = 8
    input_asset_ids: Optional[List[int]] = None


class TaskResponse(BaseModel):
    """任务响应"""
    task_id: str
    history_id: Optional[int] = None


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    status: str  # pending, processing, completed, failed
    result: Optional[List[dict]] = None
    error: Optional[dict] = None
    history_id: Optional[int] = None
    input_asset_urls: Optional[List[dict]] = None


def _load_input_assets_as_b64(input_asset_ids: List[int]) -> List[str]:
    """批量读取参考图文件,返回 base64 列表"""
    if not input_asset_ids:
        return []

    asset_map = generation_repo.load_input_assets(input_asset_ids)
    result = []

    for asset_id in input_asset_ids:
        asset = asset_map.get(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail=f'asset {asset_id} not found')

        file_path = Path(asset['location'])
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f'file not found: {asset["location"]}')

        result.append(base64.b64encode(file_path.read_bytes()).decode())

    return result


def _save_history(
    task_id: str,
    prompt: str,
    user_id: int,
    model_id: Optional[int],
    input_asset_ids: List[int],
    output_asset_ids: List[int],
    status: str,
    type_: str,
    mode: str,
    payload: dict
) -> int:
    """保存历史记录"""
    return generation_repo.save_history(
        task_id=task_id,
        prompt=prompt,
        user_id=user_id,
        model_id=model_id,
        input_asset_ids=input_asset_ids,
        output_asset_ids=output_asset_ids,
        status=status,
        type_=type_,
        mode=mode,
        payload=payload
    )


@router.post("/txt2img", response_model=TaskResponse)
async def txt2img(req: Txt2ImgRequest, user: dict = Depends(get_current_user)):
    """文生图接口"""
    user_id = user['user_id']

    if not req.prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    # 生成任务 ID
    task_id = str(uuid.uuid4())

    # 加载参考图（如果有）
    input_asset_ids = req.input_asset_ids or []
    image_b64_list = _load_input_assets_as_b64(input_asset_ids) if input_asset_ids else []

    # 获取模型信息（需要从数据库查询）
    model_info = generation_repo.get_model_info(req.model)
    if not model_info:
        raise HTTPException(status_code=404, detail=f"model {req.model} not found")

    # 获取 provider 配置（解密后的 api_key 和 base_url）
    from config import get_provider_config_by_rfid
    provider_config = get_provider_config_by_rfid(model_info['rfid'])
    if not provider_config:
        raise HTTPException(status_code=500, detail=f"provider config not found for model {req.model}")

    # 日志：打印解密后的 provider 配置（api_key 脱敏）
    api_key_masked = provider_config['api_key'][:8] + '***' if len(provider_config['api_key']) > 8 else '(too short)'
    logger.info(f'[txt2img] task_id={task_id}, model={model_info["name"]}, provider={model_info["provider"]}, '
                f'rfid={model_info["rfid"]}, api_key={api_key_masked}, base_url={provider_config["base_url"]}')

    # 保存历史记录
    type_ = 'img2img' if input_asset_ids else 'txt2img'
    payload = {
        'model': req.model,
        'prompt': req.prompt,
        'aspect_ratio': req.aspect_ratio,
        'quality': req.quality,
        'n': req.n,
        'input_asset_ids': input_asset_ids,
        'user_id': user_id
    }

    history_id = _save_history(
        task_id=task_id,
        prompt=req.prompt,
        user_id=user_id,
        model_id=req.model,
        input_asset_ids=input_asset_ids,
        output_asset_ids=[],
        status='pending',
        type_=type_,
        mode='api',
        payload=payload
    )

    # 任务入队到 Redis（完全参考 ComfyUI 原实现的平铺结构）
    task_data = {
        'task_id': task_id,
        'provider': model_info['provider'],
        'model': model_info['name'],
        'model_id': model_info['id'],
        'prompt': req.prompt,
        'aspect_ratio': req.aspect_ratio,
        'quality': req.quality,
        'n': req.n,
        'user_id': user_id,
        'api_key': provider_config['api_key'],
        'base_url': provider_config['base_url'],
        'image_b64_list': image_b64_list,
        'input_asset_ids': input_asset_ids,
        'history_id': history_id,
    }
    enqueue_task('queue:txt2img', task_data)

    logger.info(f'[txt2img] 任务已创建: {task_id}')

    return TaskResponse(task_id=task_id, history_id=history_id)


@router.post("/txt2video", response_model=TaskResponse)
async def txt2video(req: Txt2VideoRequest, user: dict = Depends(get_current_user)):
    """文生视频接口"""
    user_id = user['user_id']

    if not req.prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    # 生成任务 ID
    task_id = str(uuid.uuid4())

    # 获取模型信息
    model_info = generation_repo.get_model_info(req.model)
    if not model_info:
        raise HTTPException(status_code=404, detail=f"model {req.model} not found")

    # 获取 provider 配置
    from config import get_provider_config_by_rfid
    provider_config = get_provider_config_by_rfid(model_info['rfid'])
    if not provider_config:
        raise HTTPException(status_code=500, detail=f"provider config not found for model {req.model}")

    # 日志：打印解密后的 provider 配置（api_key 脱敏）
    api_key_masked = provider_config['api_key'][:8] + '***' if len(provider_config['api_key']) > 8 else '(too short)'
    logger.info(f'[txt2video] task_id={task_id}, model={model_info["name"]}, provider={model_info["provider"]}, '
                f'rfid={model_info["rfid"]}, api_key={api_key_masked}, base_url={provider_config["base_url"]}')

    # 保存历史记录
    payload = {
        'model': req.model,
        'prompt': req.prompt,
        'ratio': req.ratio,
        'resolution': req.resolution,
        'duration': req.duration,
        'user_id': user_id
    }

    history_id = _save_history(
        task_id=task_id,
        prompt=req.prompt,
        user_id=user_id,
        model_id=req.model,
        input_asset_ids=[],
        output_asset_ids=[],
        status='pending',
        type_='txt2video',
        mode='api',
        payload=payload
    )

    # 任务入队到 Redis（平铺结构，与 ComfyUI 原版一致）
    task_data = {
        'task_id': task_id,
        'history_id': history_id,
        'provider': model_info['provider'],
        'model': model_info['name'],
        'model_id': model_info['id'],
        'prompt': req.prompt,
        'ratio': req.ratio,
        'resolution': req.resolution,
        'duration': req.duration,
        'user_id': user_id,
        'api_key': provider_config['api_key'],
        'base_url': provider_config['base_url'],
    }
    enqueue_task('queue:txt2video', task_data)

    logger.info(f'[txt2video] 任务已创建: {task_id}')

    return TaskResponse(task_id=task_id, history_id=history_id)


@router.post("/img2video", response_model=TaskResponse)
async def img2video(req: Img2VideoRequest, user: dict = Depends(get_current_user)):
    """图生视频接口"""
    user_id = user['user_id']

    if not req.prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    # 生成任务 ID
    task_id = str(uuid.uuid4())

    input_asset_ids = req.input_asset_ids or []

    # 获取模型信息
    model_info = generation_repo.get_model_info(req.model)
    if not model_info:
        raise HTTPException(status_code=404, detail=f"model {req.model} not found")

    # 获取 provider 配置
    from config import get_provider_config_by_rfid
    provider_config = get_provider_config_by_rfid(model_info['rfid'])
    if not provider_config:
        raise HTTPException(status_code=500, detail=f"provider config not found for model {req.model}")

    # 日志：打印解密后的 provider 配置（api_key 脱敏）
    api_key_masked = provider_config['api_key'][:8] + '***' if len(provider_config['api_key']) > 8 else '(too short)'
    logger.info(f'[img2video] task_id={task_id}, model={model_info["name"]}, provider={model_info["provider"]}, '
                f'rfid={model_info["rfid"]}, api_key={api_key_masked}, base_url={provider_config["base_url"]}')

    # 保存历史记录
    payload = {
        'model': req.model,
        'prompt': req.prompt,
        'ratio': req.ratio,
        'resolution': req.resolution,
        'duration': req.duration,
        'input_asset_ids': input_asset_ids,
        'user_id': user_id
    }

    history_id = _save_history(
        task_id=task_id,
        prompt=req.prompt,
        user_id=user_id,
        model_id=req.model,
        input_asset_ids=input_asset_ids,
        output_asset_ids=[],
        status='pending',
        type_='img2video',
        mode='api',
        payload=payload
    )

    # 加载参考图（如果有）
    image_b64_list = _load_input_assets_as_b64(input_asset_ids) if input_asset_ids else []

    # 任务入队到 Redis（平铺结构，与 ComfyUI 原版一致）
    task_data = {
        'task_id': task_id,
        'history_id': history_id,
        'provider': model_info['provider'],
        'model': model_info['name'],
        'model_id': model_info['id'],
        'prompt': req.prompt,
        'ratio': req.ratio,
        'resolution': req.resolution,
        'duration': req.duration,
        'user_id': user_id,
        'api_key': provider_config['api_key'],
        'base_url': provider_config['base_url'],
        'input_asset_ids': input_asset_ids,
    }
    enqueue_task('queue:img2video', task_data)

    logger.info(f'[img2video] 任务已创建: {task_id}')

    return TaskResponse(task_id=task_id, history_id=history_id)
