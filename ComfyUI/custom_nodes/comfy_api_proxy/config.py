import os
import pathlib

# ── .env 加载 ─────────────────────────────────────────────────────────────
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
    try:
        from .repositories.provider_repo import get_default_provider
        provider = get_default_provider()
        if provider and provider.get('key'):
            return provider['key']
    except Exception:
        pass
    return os.environ.get('API_KEY', '')


def get_base_url() -> str:
    try:
        from .repositories.provider_repo import get_default_provider
        provider = get_default_provider()
        if provider and provider.get('url'):
            return provider['url'].rstrip('/')
    except Exception:
        pass
    return os.environ.get('BASE_URL', '').rstrip('/')


def save_env(api_key: str | None, base_url: str | None):
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

def get_encryption_key() -> str:
    return os.environ.get('ENCRYPTION_KEY', '')


def get_db_config() -> dict:
    return {
        'host': os.environ.get('DB_HOST', ''),
        'user': os.environ.get('DB_USER', ''),
        'password': os.environ.get('DB_PASSWORD', ''),
        'database': os.environ.get('DB_NAME', ''),
        'charset': 'utf8mb4',
    }


def get_redis_config() -> dict:
    return {
        'host': os.environ.get('REDIS_HOST', ''),
        'port': int(os.environ.get('REDIS_PORT', '6379')),
        'db': int(os.environ.get('REDIS_DB', '0')),
        'decode_responses': True,
    }


def get_output_dir() -> pathlib.Path:
    path = pathlib.Path(os.environ.get('OUTPUT_DIR', '/app/output'))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_input_dir() -> pathlib.Path:
    path = pathlib.Path(os.environ.get('INPUT_DIR', '/app/input'))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_worker_count() -> int:
    return int(os.environ.get('WORKER_COUNT', '4'))


def get_queue_max_size() -> int:
    return int(os.environ.get('QUEUE_MAX_SIZE', '20'))


def get_oss_config() -> dict:
    return {
        'access_key_id': os.environ.get('OSS_ACCESS_KEY_ID', ''),
        'access_key_secret': os.environ.get('OSS_ACCESS_KEY_SECRET', ''),
        'bucket_name': os.environ.get('OSS_BUCKET_NAME', ''),
        'endpoint': os.environ.get('OSS_ENDPOINT', ''),
    }


# ── Provider 配置查询（供 worker.py 独立运行时使用）────────────────────────

def get_provider_config_by_id(provider_id: str) -> tuple[str, str] | None:
    try:
        from .repositories.provider_repo import get_provider_by_id
        provider = get_provider_by_id(int(provider_id))
        if provider:
            return provider['key'], provider['url'].rstrip('/')
    except Exception:
        pass
    return None


def get_default_provider_config() -> dict | None:
    try:
        from .repositories.provider_repo import get_default_provider
        provider = get_default_provider()
        if provider:
            return {
                'id': provider['id'],
                'base_url': provider['url'],
                'api_key': provider['key'],
            }
    except Exception:
        pass
    return None
