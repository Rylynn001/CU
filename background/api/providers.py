"""模型提供商相关路由"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from repositories import provider_repo

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
    provider = provider_repo.get_default_provider()
    return {
        'base_url': provider['url'] if provider else '',
        'has_key': bool(provider and provider['key'])
    }


@router.put("/config")
async def update_config(config: ConfigUpdate):
    """保存配置（API Key 和 Base URL）"""
    if config.api_key:
        provider_repo.update_provider_key(config.api_key)

    if config.base_url:
        provider_repo.update_provider_url(config.base_url)

    return {'ok': True}


@router.get("/providers")
async def get_providers():
    """获取所有提供商"""
    providers = provider_repo.get_all_providers()
    return {'providers': providers}


@router.get("/providers/{provider_id}/models")
async def get_provider_models(provider_id: int):
    """获取指定提供商的模型"""
    models = provider_repo.get_provider_models(provider_id)
    return {'models': models}


@router.get("/models")
async def get_models(provider_id: int = None, type: str = None):
    """获取模型列表"""
    models = provider_repo.get_all_models(provider_id)

    if type:
        models = [m for m in models if m.get('type') == type]

    return {'models': models}


@router.post("/models")
async def add_model(model: ModelCreate):
    """新增模型"""
    provider = provider_repo.get_default_provider_id()

    if not provider:
        raise HTTPException(status_code=400, detail='未找到默认提供商')

    provider_id = provider['id']

    model_id = provider_repo.create_model(
        provider_id, model.name, model.description, model.type, model.id
    )

    return {'id': model_id, 'ok': True}


@router.delete("/models/{model_id}")
async def delete_model(model_id: int):
    """删除模型"""
    result = provider_repo.delete_model(model_id)

    if result == 0:
        raise HTTPException(status_code=404, detail=f'model {model_id} not found')

    return {'ok': True}
