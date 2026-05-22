"""Provider 配置查找逻辑"""
import logging
from aiohttp import web
from .. import config as cfg
from ..repositories import provider_repo

logger = logging.getLogger('comfy_api_proxy')


def get_provider_config(provider_id: int | None = None, model_id: int | None = None) -> tuple[str, str]:
    """
    返回 (api_key, base_url)。
    优先级：provider_id > model_id 推导 > 默认提供商 > .env
    """
    if model_id and not provider_id:
        model = provider_repo.get_model_by_id(model_id)
        if model:
            provider_id = model.get('rfid')
        else:
            logger.warning(f'[provider] model {model_id} not found, using default')

    if provider_id:
        result = cfg.get_provider_config_by_id(str(provider_id))
        if not result:
            raise web.HTTPNotFound(reason=f'provider {provider_id} not found')
        return result

    default = cfg.get_default_provider_config()
    if default:
        return default['api_key'], default['base_url']

    api_key = cfg.get_api_key()
    base_url = cfg.get_base_url()
    if not api_key:
        raise web.HTTPServiceUnavailable(reason='API_KEY not configured')
    if not base_url:
        raise web.HTTPServiceUnavailable(reason='BASE_URL not configured')
    return api_key, base_url


def detect_provider(model_name: str) -> str:
    """根据模型名称判断供应商：openai | gemini | generic"""
    m = model_name.lower()
    if any(x in m for x in ['gpt', 'dalle', 'mcs7c']):
        return 'openai'
    if 'gemini' in m:
        return 'gemini'
    return 'generic'


def get_model_info(model_id: int) -> dict:
    """查询模型信息，不存在则抛 404"""
    model = provider_repo.get_model_by_id(model_id)
    if not model:
        raise web.HTTPNotFound(reason=f'model {model_id} not found')
    return model
