"""任务管理相关路由（Redis 队列）"""
import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import redis

from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Redis 客户端
_redis_client = None
REDIS_AVAILABLE = False


def get_redis():
    """获取 Redis 客户端"""
    global _redis_client, REDIS_AVAILABLE
    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True
            )
            _redis_client.ping()
            REDIS_AVAILABLE = True
            logger.info("Redis 已连接")
        except Exception as e:
            REDIS_AVAILABLE = False
            logger.warning(f"Redis 不可用: {e}")
    return _redis_client


class TaskSubmit(BaseModel):
    task_type: str
    payload: dict


class TaskStatusUpdate(BaseModel):
    status: str
    result: dict | None = None


@router.post("/tasks/submit")
async def submit_task(req: TaskSubmit):
    """提交任务到队列"""
    if not REDIS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Redis 不可用")

    client = get_redis()
    queue_name = f"queue:{req.task_type}"

    # 入队
    client.lpush(queue_name, json.dumps(req.payload))

    return {'ok': True, 'queue': queue_name}


@router.get("/tasks/queue/{queue_name}")
async def get_queue_status(queue_name: str):
    """获取队列状态"""
    if not REDIS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Redis 不可用")

    client = get_redis()
    length = client.llen(queue_name)

    return {'queue': queue_name, 'length': length}


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态（前端调用路径）"""
    if not REDIS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Redis 不可用")

    client = get_redis()
    status = client.get(f"task:{task_id}:status")

    if not status:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found or expired")

    response = {'status': status}

    # 如果任务完成或失败，获取结果
    if status in ('completed', 'failed'):
        result_json = client.get(f"task:{task_id}:result")
        if result_json:
            result_data = json.loads(result_json)
            if status == 'completed':
                response['result'] = result_data.get('result', [])
                if result_data.get('history_id'):
                    response['history_id'] = result_data['history_id']
            else:
                response['error'] = result_data.get('error')
                if result_data.get('history_id'):
                    response['history_id'] = result_data['history_id']

    return response


@router.put("/tasks/{task_id}/status")
async def update_task_status(task_id: str, req: TaskStatusUpdate):
    """更新任务状态"""
    if not REDIS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Redis 不可用")

    client = get_redis()
    client.setex(f"task:{task_id}:status", 3600, req.status)

    if req.result:
        client.setex(f"task:{task_id}:result", 3600, json.dumps(req.result))

    return {'ok': True}


@router.get("/tasks/{task_id}/result")
async def get_task_result(task_id: str):
    """获取任务结果"""
    if not REDIS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Redis 不可用")

    client = get_redis()
    result_json = client.get(f"task:{task_id}:result")

    if not result_json:
        raise HTTPException(status_code=404, detail="任务结果不存在")

    return {'task_id': task_id, 'result': json.loads(result_json)}


@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消任务"""
    if not REDIS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Redis 不可用")

    client = get_redis()
    client.setex(f"task:{task_id}:status", 3600, 'failed')
    client.setex(
        f"task:{task_id}:result",
        3600,
        json.dumps({'error': {'error_message': '任务已被用户取消'}})
    )
    logger.info(f"任务 {task_id} 已取消")
    return {'ok': True}


@router.post("/task/{task_id}/priority")
async def prioritize_task(task_id: str):
    """任务插队（提高优先级）"""
    if not REDIS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Redis 不可用")

    client = get_redis()
    status = client.get(f"task:{task_id}:status")

    if not status:
        raise HTTPException(status_code=404, detail="Task not found")

    if status != 'pending':
        raise HTTPException(status_code=400, detail=f"Task is {status}, cannot prioritize")

    # 简单实现：标记为高优先级
    client.setex(f"task:{task_id}:priority", 3600, 'high')
    logger.info(f"任务 {task_id} 已提高优先级")
    return {'ok': True}



# 初始化 Redis 连接
get_redis()
