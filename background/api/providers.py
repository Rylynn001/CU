"""模型提供商相关路由"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import execute_query

router = APIRouter()


class ConfigResponse(BaseModel):
    base_url: str
    has_key: bool


class ConfigUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None


class ModelCreate(BaseModel):
    id: str
    name: str
    description: str
    type: str = 'image'  # 'image' 或 'video'


@router.get("/config", response_model=ConfigResponse)
async def get_config():
    """获取配置"""
    provider = execute_query(
        'SELECT url, `key` FROM provider WHERE is_default = 1 LIMIT 1',
        fetch_one=True
    )
    return {
        'base_url': provider['url'] if provider else '',
        'has_key': bool(provider and provider['key'])
    }


@router.put("/config")
async def update_config(config: ConfigUpdate):
    """保存配置（API Key 和 Base URL）"""
    if config.api_key:
        # 更新默认提供商的 key
        execute_query(
            'UPDATE provider SET `key` = %s WHERE is_default = 1',
            (config.api_key,)
        )

    if config.base_url:
        # 更新默认提供商的 url
        execute_query(
            'UPDATE provider SET url = %s WHERE is_default = 1',
            (config.base_url,)
        )

    return {'ok': True}


@router.get("/providers")
async def get_providers():
    """获取所有提供商"""
    providers = execute_query(
        'SELECT id, name, url, type FROM provider ORDER BY id',
        fetch_all=True
    )
    return {'providers': providers or []}


@router.get("/providers/{provider_id}/models")
async def get_provider_models(provider_id: int):
    """获取指定提供商的模型"""
    models = execute_query(
        'SELECT id, rfid, name, description, type, provider FROM api_models WHERE rfid = %s ORDER BY id',
        (provider_id,),
        fetch_all=True
    )
    return {'models': models or []}


@router.get("/models")
async def get_models(provider_id: int = None, type: str = None):
    """获取模型列表"""
    if provider_id:
        query = 'SELECT id, rfid, name, description, type, provider FROM api_models WHERE rfid = %s'
        params = (provider_id,)
    else:
        query = 'SELECT id, rfid, name, description, type, provider FROM api_models'
        params = None

    models = execute_query(query, params, fetch_all=True) or []

    if type:
        models = [m for m in models if m.get('type') == type]

    return {'models': models}


@router.post("/models")
async def add_model(model: ModelCreate):
    """新增模型"""
    # 获取默认提供商 ID
    provider = execute_query(
        'SELECT id FROM provider WHERE is_default = 1 LIMIT 1',
        fetch_one=True
    )

    if not provider:
        raise HTTPException(status_code=400, detail='未找到默认提供商')

    provider_id = provider['id']

    # 插入模型
    model_id = execute_query(
        '''INSERT INTO api_models (rfid, name, description, type, provider, created_at)
           VALUES (%s, %s, %s, %s, %s, NOW())''',
        (provider_id, model.name, model.description, model.type, model.id)
    )

    return {'id': model_id, 'ok': True}


@router.delete("/models/{model_id}")
async def delete_model(model_id: int):
    """删除模型"""
    result = execute_query(
        'DELETE FROM api_models WHERE id = %s',
        (model_id,)
    )

    if result == 0:
        raise HTTPException(status_code=404, detail=f'model {model_id} not found')

    return {'ok': True}
