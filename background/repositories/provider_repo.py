"""模型提供商相关的数据库操作"""
import logging
import json
from database import execute_query
from core.aspect_ratios import model_parameter_config

logger = logging.getLogger(__name__)


def get_default_provider():
    """获取默认提供商配置"""
    provider = execute_query(
        'SELECT url, `key` FROM provider WHERE is_default = 1 LIMIT 1',
        fetch_one=True
    )
    return provider


def update_provider_key(api_key: str):
    """更新默认提供商的 API Key"""
    execute_query(
        'UPDATE provider SET `key` = %s WHERE is_default = 1',
        (api_key,)
    )


def update_provider_url(base_url: str):
    """更新默认提供商的 Base URL"""
    execute_query(
        'UPDATE provider SET url = %s WHERE is_default = 1',
        (base_url,)
    )


def get_all_providers():
    """获取所有提供商"""
    providers = execute_query(
        'SELECT id, name, url, type FROM provider ORDER BY id',
        fetch_all=True
    )
    return providers or []


def get_provider_models(provider_id: int):
    """获取指定提供商的模型"""
    models = execute_query(
        'SELECT id, rfid, name, description, type, provider, context_window, parameters FROM api_models WHERE rfid = %s ORDER BY id',
        (provider_id,),
        fetch_all=True
    )
    for model in models or []:
        if isinstance(model.get('parameters'), str):
            model['parameters'] = json.loads(model['parameters'])
    return models or []


def get_all_models(provider_id: int = None):
    """获取模型列表"""
    if provider_id:
        query = 'SELECT id, rfid, name, description, type, provider, context_window, parameters FROM api_models WHERE rfid = %s'
        params = (provider_id,)
    else:
        query = 'SELECT id, rfid, name, description, type, provider, context_window, parameters FROM api_models'
        params = None

    models = execute_query(query, params, fetch_all=True) or []
    for model in models:
        if isinstance(model.get('parameters'), str):
            model['parameters'] = json.loads(model['parameters'])
    return models


def get_default_provider_id():
    """获取默认提供商ID"""
    provider = execute_query(
        'SELECT id FROM provider WHERE is_default = 1 LIMIT 1',
        fetch_one=True
    )
    return provider


def create_model(provider_id: int, name: str, description: str, model_type: str, provider: str, parameters: dict | None = None):
    """新增模型"""
    if model_type in ('image', 'video'):
        parameters = model_parameter_config(model_type, parameters)
    model_id = execute_query(
        '''INSERT INTO api_models (rfid, name, description, type, provider, parameters, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, NOW())''',
        (provider_id, name, description, model_type, provider, json.dumps(parameters, ensure_ascii=False) if parameters else None)
    )
    return model_id


def delete_model(model_id: int):
    """删除模型"""
    result = execute_query(
        'DELETE FROM api_models WHERE id = %s',
        (model_id,)
    )
    return result


def get_provider_by_id(provider_id: int):
    """根据 provider ID 获取配置（不解密）"""
    provider = execute_query(
        'SELECT * FROM api_providers WHERE id = %s LIMIT 1',
        (provider_id,),
        fetch_one=True
    )
    return provider
