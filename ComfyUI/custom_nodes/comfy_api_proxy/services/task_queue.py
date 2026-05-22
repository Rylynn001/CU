"""Redis 任务队列统一封装"""
import json
import logging
import redis
from ..config import get_redis_config

logger = logging.getLogger('comfy_api_proxy')

_client: redis.Redis | None = None
AVAILABLE = False


def get_client() -> redis.Redis:
    global _client, AVAILABLE
    if _client is None:
        _client = redis.Redis(**get_redis_config())
        try:
            _client.ping()
            AVAILABLE = True
            logger.info('[task_queue] Redis connected')
        except Exception as e:
            AVAILABLE = False
            logger.warning(f'[task_queue] Redis not available: {e}')
    return _client


# ── 队列操作 ──────────────────────────────────────────────────────────────

def enqueue(queue_name: str, payload: dict) -> None:
    get_client().lpush(queue_name, json.dumps(payload))


def queue_length(queue_name: str) -> int:
    return get_client().llen(queue_name)


def list_queue(queue_name: str) -> list[dict]:
    client = get_client()
    length = client.llen(queue_name)
    items = []
    for i in range(length):
        raw = client.lindex(queue_name, i)
        if raw:
            items.append(json.loads(raw))
    return items


def remove_from_queue(queue_name: str, task_json: str) -> None:
    get_client().lrem(queue_name, 1, task_json)


def push_to_front(queue_name: str, task_json: str) -> None:
    get_client().rpush(queue_name, task_json)


# ── 任务状态 ──────────────────────────────────────────────────────────────

def set_status(task_id: str, status: str, ttl: int = 3600) -> None:
    get_client().setex(f'task:{task_id}:status', ttl, status)


def get_status(task_id: str) -> str | None:
    return get_client().get(f'task:{task_id}:status')


def set_result(task_id: str, result: dict, ttl: int = 3600) -> None:
    get_client().setex(f'task:{task_id}:result', ttl, json.dumps(result))


def get_result(task_id: str) -> dict | None:
    raw = get_client().get(f'task:{task_id}:result')
    return json.loads(raw) if raw else None


def set_meta(task_id: str, key: str, value: str, ttl: int = 3600) -> None:
    get_client().setex(f'task:{task_id}:{key}', ttl, value)


def get_meta(task_id: str, key: str) -> str | None:
    return get_client().get(f'task:{task_id}:{key}')


def delete_meta(task_id: str, *keys: str) -> None:
    client = get_client()
    for key in keys:
        client.delete(f'task:{task_id}:{key}')


def set_downloading_lock(task_id: str, ttl: int = 1200) -> None:
    get_client().setex(f'task:{task_id}:downloading', ttl, '1')


def is_downloading(task_id: str) -> bool:
    return bool(get_client().get(f'task:{task_id}:downloading'))


def release_downloading_lock(task_id: str) -> None:
    get_client().delete(f'task:{task_id}:downloading')


def mark_pending(task_id: str) -> None:
    import asyncio
    client = get_client()
    client.setex(f'task:{task_id}:status', 3600, 'pending')
    try:
        client.setex(f'task:{task_id}:created_at', 3600, str(asyncio.get_event_loop().time()))
    except Exception:
        pass
