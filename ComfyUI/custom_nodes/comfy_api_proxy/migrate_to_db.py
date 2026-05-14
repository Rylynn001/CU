"""数据迁移脚本：从 .env 和 models_config.json 迁移到数据库"""
import logging
from . import config as cfg
from . import db_queries

logger = logging.getLogger('comfy_api_proxy')


def migrate_env_to_db():
    """将 .env 中的配置迁移到数据库作为默认提供商"""
    api_key = cfg.get_api_key()
    base_url = cfg.get_base_url()

    if not api_key or not base_url:
        logger.info('[migrate] No .env config found, skipping migration')
        return

    # 检查是否已有默认提供商
    existing = db_queries.get_default_provider()
    if existing:
        logger.info('[migrate] Default provider already exists, skipping .env migration')
        return

    # 创建默认提供商
    try:
        provider = db_queries.create_provider(
            name='默认提供商',
            base_url=base_url,
            api_key=api_key,
            is_default=True,
            is_active=True,
            description='从 .env 文件迁移'
        )
        logger.info(f'[migrate] Created default provider from .env: {provider["id"]}')
        return provider
    except Exception as e:
        logger.error(f'[migrate] Failed to create provider from .env: {e}')
        return None


def migrate_models_to_db(provider_id: str):
    """将 models_config.json 中的模型迁移到数据库"""
    models = cfg.load_models()

    if not models:
        logger.info('[migrate] No models found in models_config.json, skipping migration')
        return

    migrated_count = 0
    for model in models:
        model_id = model.get('id', '').strip()
        name = model.get('name', '').strip()
        description = model.get('description', '').strip() or None
        model_type = model.get('type', 'image').strip()

        if not model_id or not name:
            logger.warning(f'[migrate] Skipping invalid model: {model}')
            continue

        # 检查是否已存在
        existing = db_queries.get_model_by_model_id(model_id, provider_id)
        if existing:
            logger.info(f'[migrate] Model {model_id} already exists, skipping')
            continue

        try:
            db_queries.create_model(
                provider_id=provider_id,
                model_id=model_id,
                name=name,
                description=description,
                model_type=model_type,
                is_active=True,
                sort_order=0
            )
            migrated_count += 1
            logger.info(f'[migrate] Migrated model: {model_id}')
        except Exception as e:
            logger.error(f'[migrate] Failed to migrate model {model_id}: {e}')

    logger.info(f'[migrate] Migrated {migrated_count} models to database')


def run_migration():
    """执行完整的数据迁移"""
    logger.info('[migrate] Starting data migration...')

    # 1. 迁移 .env 配置
    provider = migrate_env_to_db()

    # 2. 迁移模型配置
    if provider:
        migrate_models_to_db(provider['id'])
    else:
        # 如果没有创建新提供商，尝试使用现有的默认提供商
        existing = db_queries.get_default_provider()
        if existing:
            migrate_models_to_db(existing['id'])

    logger.info('[migrate] Data migration completed')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_migration()
