import os
import json
import pathlib

# ── .env 加载（python-dotenv 可选，没装就手动读）──────────────────────────
_env_path = pathlib.Path(__file__).parent / '.env'

def _load_env():
    if not _env_path.exists():
        return
    with open(_env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

_load_env()

def get_api_key() -> str:
    """获取 API Key（优先从数据库默认提供商，回退到 .env）"""
    try:
        from . import db_queries
        provider = db_queries.get_default_provider()
        if provider and provider.get('key'):
            return provider['key']
    except Exception:
        pass
    return os.environ.get('API_KEY', '')

def get_base_url() -> str:
    """获取 Base URL（优先从数据库默认提供商，回退到 .env）"""
    try:
        from . import db_queries
        provider = db_queries.get_default_provider()
        if provider and provider.get('url'):
            return provider['url'].rstrip('/')
    except Exception:
        pass
    return os.environ.get('BASE_URL', '').rstrip('/')

def save_env(api_key: str | None, base_url: str | None):
    """更新 .env 文件中的 API_KEY / BASE_URL"""
    data: dict[str, str] = {}
    if _env_path.exists():
        with open(_env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                data[k.strip()] = v.strip()
    if api_key is not None:
        data['API_KEY'] = api_key
        os.environ['API_KEY'] = api_key
    if base_url is not None:
        data['BASE_URL'] = base_url
        os.environ['BASE_URL'] = base_url
    with open(_env_path, 'w', encoding='utf-8') as f:
        for k, v in data.items():
            f.write(f'{k}={v}\n')

# ── 数据库配置 ────────────────────────────────────────────────────────────

def get_db_config() -> dict:
    """获取数据库配置"""
    return {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD', '123456'),
        'database': os.environ.get('DB_NAME', 'comfyui'),
        'charset': 'utf8mb4',
    }

def get_redis_config() -> dict:
    """获取 Redis 配置"""
    return {
        'host': os.environ.get('REDIS_HOST', 'localhost'),
        'port': int(os.environ.get('REDIS_PORT', '6379')),
        'db': int(os.environ.get('REDIS_DB', '0')),
        'decode_responses': True,
    }

def get_output_dir() -> pathlib.Path:
    """获取输出目录"""
    path = pathlib.Path(os.environ.get('OUTPUT_DIR', '/app/output'))
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_input_dir() -> pathlib.Path:
    """获取输入目录"""
    path = pathlib.Path(os.environ.get('INPUT_DIR', '/app/input'))
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_oss_config() -> dict:
    """获取 OSS 配置"""
    return {
        'access_key_id': os.environ.get('OSS_ACCESS_KEY_ID', ''),
        'access_key_secret': os.environ.get('OSS_ACCESS_KEY_SECRET', ''),
        'bucket_name': os.environ.get('OSS_BUCKET_NAME', ''),
        'endpoint': os.environ.get('OSS_ENDPOINT', ''),
    }

# ── models_config.json ────────────────────────────────────────────────────
_models_path = pathlib.Path(__file__).parent / 'models_config.json'

def load_models() -> list[dict]:
    if not _models_path.exists():
        return []
    with open(_models_path, encoding='utf-8') as f:
        return json.load(f)

def save_models(models: list[dict]):
    with open(_models_path, 'w', encoding='utf-8') as f:
        json.dump(models, f, ensure_ascii=False, indent=2)


# ── 数据库提供商和模型查询 ──────────────────────────────────────────────────

def _get_db_queries():
    """延迟导入 db_queries，避免循环导入"""
    try:
        from . import db_queries
        return db_queries
    except ImportError:
        # 作为独立脚本运行时（如 worker.py）
        import db_queries
        return db_queries


def get_provider_config_by_id(provider_id: str) -> tuple[str, str] | None:
    """通过 provider_id 获取 api_key 和 base_url"""
    try:
        db_queries = _get_db_queries()
        provider = db_queries.get_provider_by_id(int(provider_id))
        if provider:
            return provider['key'], provider['url'].rstrip('/')
    except Exception:
        pass
    return None


def get_default_provider_config() -> dict | None:
    """从数据库获取默认提供商配置"""
    try:
        db_queries = _get_db_queries()
        provider = db_queries.get_default_provider()
        if provider:
            return {
                'id': provider['id'],
                'base_url': provider['url'],
                'api_key': provider['key'],
            }
    except Exception:
        pass
    return None


def get_provider_config(provider_id: str) -> dict | None:
    """根据ID获取提供商配置"""
    try:
        db_queries = _get_db_queries()
        provider = db_queries.get_provider_by_id(int(provider_id))
        if provider:
            return {
                'id': provider['id'],
                'base_url': provider['url'],
                'api_key': provider['key'],
            }
    except Exception:
        pass
    return None


def get_models_from_db(provider_id: str | None = None) -> list[dict]:
    """从数据库获取模型列表"""
    try:
        db_queries = _get_db_queries()
        models = db_queries.get_all_models(provider_id=int(provider_id) if provider_id else None)
        return [
            {
                'id': m['id'],
                'name': m['name'],
                'description': m['description'],
                'type': m['type'],
                'provider_id': m['rfid'],
            }
            for m in models
        ]
    except Exception:
        return []
