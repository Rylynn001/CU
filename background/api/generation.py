"""图片和视频生成接口（从 ComfyUI 迁移）"""
import uuid
import json
import base64
import logging
import redis
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from repositories import generation_repo
from core.aspect_ratios import normalize_parameters, provider_parameters
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
    # 标记和入队原子完成。计划恢复时使用同一 task_id，不重复提交生成。
    client.eval("""
        if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
        redis.call('SET', KEYS[1], '1')
        redis.call('SETEX', KEYS[2], 3600, 'pending')
        redis.call('LPUSH', KEYS[3], ARGV[1])
        return 1
    """, 3, f"task:{task_data['task_id']}:enqueued", f"task:{task_data['task_id']}:status",
        queue_name, json.dumps(task_data, ensure_ascii=False))


class Txt2ImgRequest(BaseModel):
    """文生图请求"""
    model: int
    prompt: str
    parameters: dict = Field(default_factory=dict)
    # 兼容旧客户端，新的前端使用 parameters。
    aspect_ratio: Optional[str] = None
    quality: Optional[str] = None
    n: Optional[int] = None
    input_asset_ids: Optional[List[int]] = None


class Txt2VideoRequest(BaseModel):
    """文生视频请求(支持图生视频)"""
    model: int
    prompt: str
    parameters: dict = Field(default_factory=dict)
    aspect_ratio: Optional[str] = None
    # 兼容旧客户端，新的请求统一使用 aspect_ratio。
    ratio: Optional[str] = None
    resolution: Optional[str] = None
    duration: Optional[int] = None
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


def _validate_model_references(model_info: dict, input_asset_ids: List[int], allow_video: bool) -> None:
    """按模型 JSON 中的 references 能力校验参考素材数量和类型。"""
    if not input_asset_ids:
        return

    assets = generation_repo.load_input_assets(input_asset_ids)
    image_count = 0
    video_count = 0
    for asset_id in input_asset_ids:
        asset = assets.get(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail=f'asset {asset_id} not found')
        if asset.get('asset_type') == 'video':
            video_count += 1
        else:
            image_count += 1

    validate_reference_counts(model_info, image_count, video_count, allow_video)


def validate_reference_counts(model_info: dict, image_count: int, video_count: int, allow_video: bool):
    config = model_info.get('parameters') or {}
    references = config.get('references') or {}
    image_config = references.get('images') or {}
    video_config = references.get('videos') or {}
    image_max = image_config.get('max', 12 if not references else 0)
    video_max = video_config.get('max', 0)
    if image_count and image_config and not image_config.get('supported', False):
        raise HTTPException(status_code=400, detail=f'模型 {model_info["name"]} 不支持图片参考素材')
    if video_count and (not allow_video or not video_config.get('supported', False)):
        raise HTTPException(status_code=400, detail=f'模型 {model_info["name"]} 不支持视频参考素材')
    if image_count > image_max:
        raise HTTPException(status_code=400, detail=f'模型 {model_info["name"]} 最多支持 {image_max} 张图片参考素材')
    if video_count > video_max:
        raise HTTPException(status_code=400, detail=f'模型 {model_info["name"]} 最多支持 {video_max} 个视频参考素材')


def normalize_generation_parameters(media_type: str, parameters: dict) -> dict:
    try:
        return normalize_parameters(media_type, parameters)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


async def submit_generation_task(req, user: dict, media_type: str, *, task_id: str | None = None):
    """统一校验、写历史和入队；后台计划用固定编号恢复未完成的提交。"""
    from config import get_provider_config_by_rfid
    from agents.services.chat_assets import load_chat_assets

    user_id = user['user_id']
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail='生成描述不能为空')
    task_id = task_id or str(uuid.uuid4())
    existing = generation_repo.get_task_history(task_id, user_id)
    if existing and (existing['status'] != 'pending' or get_redis().exists(f'task:{task_id}:enqueued')):
        return TaskResponse(task_id=task_id, history_id=existing['id'])

    input_asset_ids = req.input_asset_ids or []
    if input_asset_ids:
        load_chat_assets(input_asset_ids, user_id)
    model_info = generation_repo.get_model_info(req.model)
    if not model_info:
        raise HTTPException(status_code=404, detail=f'模型 {req.model} 不存在')
    providers = ('openai', 'gemini') if media_type == 'image' else ('ark', 'openai')
    if model_info['type'] != media_type or model_info['provider'] not in providers:
        raise HTTPException(status_code=400, detail='模型类型或供应商不支持此生成任务')
    _validate_model_references(model_info, input_asset_ids, allow_video=media_type == 'video')
    provider_config = get_provider_config_by_rfid(model_info['rfid'])
    if not provider_config:
        raise HTTPException(status_code=400, detail='模型未配置供应商')

    keys = ('aspect_ratio', 'quality', 'n') if media_type == 'image' else ('aspect_ratio', 'ratio', 'resolution', 'duration')
    parameters = {key: getattr(req, key) for key in keys if getattr(req, key) is not None}
    parameters.update(req.parameters or {})
    parameters = normalize_generation_parameters(media_type, parameters)
    try:
        provider_parameters(media_type, model_info['provider'], model_info['name'], parameters)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    payload = {'model': req.model, 'prompt': req.prompt, 'parameters': parameters,
               'input_asset_ids': input_asset_ids, 'user_id': user_id}
    history_id = existing['id'] if existing else generation_repo.save_history(
        task_id=task_id, prompt=req.prompt, user_id=user_id, model_id=req.model,
        input_asset_ids=input_asset_ids, output_asset_ids=[], status='pending',
        type_='img2img' if media_type == 'image' and input_asset_ids else ('txt2img' if media_type == 'image' else 'txt2video'),
        mode='api', payload=payload,
    )
    task_data = {
        'task_id': task_id, 'history_id': history_id, 'provider': model_info['provider'],
        'model': model_info['name'], 'model_id': model_info['id'], 'prompt': req.prompt,
        'parameters': parameters, 'user_id': user_id, 'api_key': provider_config['api_key'],
        'base_url': provider_config['base_url'], 'input_asset_ids': input_asset_ids,
    }
    if media_type == 'image':
        task_data['image_b64_list'] = _load_input_assets_as_b64(input_asset_ids)
    enqueue_task('queue:txt2img' if media_type == 'image' else 'queue:txt2video', task_data)
    logger.info('生成任务入队 task_id=%s history_id=%s media_type=%s', task_id, history_id, media_type)
    return TaskResponse(task_id=task_id, history_id=history_id)


@router.post('/txt2img', response_model=TaskResponse)
async def txt2img(req: Txt2ImgRequest, user: dict = Depends(get_current_user)):
    return await submit_generation_task(req, user, 'image')


@router.post('/txt2video', response_model=TaskResponse)
async def txt2video(req: Txt2VideoRequest, user: dict = Depends(get_current_user)):
    return await submit_generation_task(req, user, 'video')
