"""任务管理相关路由（Redis 队列）"""
import json
import logging
import uuid
import pathlib
import asyncio
import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import redis

from config import settings
from core import parse_ark_response_error

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


async def _download_video(task_id: str, video_url: str, stored_user_id: str | None) -> tuple[str, int | None]:
    """下载视频到 OUTPUT_DIR，写入 assets 表，返回 (local_url, asset_id)"""
    from repositories.asset_repo import save_output_asset

    OUTPUT_DIR = pathlib.Path(settings.OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.mp4'
    save_path = OUTPUT_DIR / filename

    max_retries = 3
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=600)) as resp:
                    if resp.status != 200:
                        raise Exception(f'下载视频失败: HTTP {resp.status}')
                    expected_size = resp.content_length
                    written = 0
                    with open(save_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(1 << 16):
                            f.write(chunk)
                            written += len(chunk)
            # 校验下载完整性
            if expected_size is not None and written < expected_size:
                raise Exception(f'视频下载不完整: {written}/{expected_size} 字节')
            logger.info(f"[{task_id}] 视频下载成功: {save_path}")
            break
        except Exception as e:
            last_error = e
            save_path.unlink(missing_ok=True)
            logger.warning(f'[{task_id}] 视频下载失败(第 {attempt}/{max_retries} 次): {e}')
            if attempt < max_retries:
                await asyncio.sleep(2 * attempt)
    else:
        raise Exception(f'视频下载重试 {max_retries} 次仍失败: {last_error}')

    local_url = f'/api/api-proxy/output/{filename}'

    output_asset_id = None
    if stored_user_id:
        try:
            output_asset_id = save_output_asset(str(save_path), int(stored_user_id), 'video')
            logger.info(f'[{task_id}] 视频已写入资产表, asset_id={output_asset_id}')
        except Exception as e:
            logger.error(f'[{task_id}] 写入资产表失败: {e}')

    return local_url, output_asset_id


async def _poll_ark_task(task_id: str, remote_id: str, api_key: str, base_url: str | None, stored_user_id: str | None):
    """轮询 Ark 任务状态，完成后下载视频并更新 Redis"""
    try:
        from openai import OpenAI

        logger.info(f"[轮询] task_id={task_id}, remote_id={remote_id}, base_url={base_url}, api_key={'***' + api_key[-4:] if api_key and len(api_key) > 4 else 'None'}")

        client = OpenAI(api_key=api_key, base_url=base_url)
        result = client.get(f"/contents/generations/tasks/{remote_id}", cast_to=object)
        remote_status = result.get("status")

        logger.info(f'[轮询] task_id={task_id}, remote_id={remote_id}, Ark 返回状态: {remote_status}')

        redis_client = get_redis()

        if remote_status == "succeeded":
            video_url = result.get("content", {}).get("video_url")
            if not video_url:
                raise Exception('Ark 响应中无 video_url')

            logger.info(f"[轮询] task_id={task_id}, 开始下载视频: {video_url}")

            # 设置下载锁
            redis_client.setex(f"task:{task_id}:downloading", 300, '1')
            try:
                local_url, output_asset_id = await _download_video(task_id, video_url, stored_user_id)

                # 更新历史记录
                from repositories.history_repo import update_history
                history_id_raw = redis_client.get(f"task:{task_id}:history_id")
                if history_id_raw:
                    history_id = int(history_id_raw)
                    update_history(
                        history_id=history_id,
                        output_asset_ids=[output_asset_id] if output_asset_id else [],
                        status='done',
                        message=None
                    )
                    logger.info(f"[轮询] task_id={task_id}, 已更新 history_id={history_id}")
                else:
                    history_id = None
                    logger.warning(f"[轮询] task_id={task_id}, 未找到 history_id")

                # 更新任务状态
                redis_client.setex(f"task:{task_id}:status", 3600, 'completed')
                redis_client.setex(
                    f"task:{task_id}:result",
                    3600,
                    json.dumps({
                        'result': [{'url': local_url, 'type': 'video', 'asset_id': output_asset_id}],
                        'history_id': history_id,
                    })
                )

                # 清理元数据
                redis_client.delete(
                    f"task:{task_id}:remote_id",
                    f"task:{task_id}:api_key",
                    f"task:{task_id}:base_url",
                    f"task:{task_id}:provider",
                    f"task:{task_id}:user_id",
                    f"task:{task_id}:downloading"
                )

                logger.info(f"[轮询] task_id={task_id}, 已标记为 completed")
                return {
                    'status': 'completed',
                    'result': [{'url': local_url, 'type': 'video', 'asset_id': output_asset_id}],
                    'history_id': history_id,
                }
            except Exception as download_error:
                redis_client.delete(f"task:{task_id}:downloading")
                logger.error(f'[轮询] task_id={task_id}, 下载视频失败，将在下次轮询重试: {download_error}')
                return None

        elif remote_status == "failed":
            error_info = result.get("error") if isinstance(result, dict) else None
            error_code = (error_info.get("code") if isinstance(error_info, dict) else None) or ""
            error_message = (error_info.get("message") if isinstance(error_info, dict) else None) or ""

            # 转换为用户友好提示
            friendly_error = parse_ark_response_error(error_code, error_message)

            logger.error(
                f'[轮询] task_id={task_id}, Ark 任务失败: {friendly_error}',
                extra={'error_code': error_code, 'raw_message': error_message, 'full_response': result}
            )

            # 更新历史记录
            from repositories.history_repo import update_history
            history_id_raw = redis_client.get(f"task:{task_id}:history_id")
            if history_id_raw:
                history_id = int(history_id_raw)
                update_history(history_id=history_id, output_asset_ids=[], status='error', message=friendly_error)
                logger.info(f"[轮询] task_id={task_id}, 已更新 history_id={history_id} 为失败状态")
            else:
                history_id = None

            # 更新任务状态
            redis_client.setex(f"task:{task_id}:status", 3600, 'failed')
            redis_client.setex(
                f"task:{task_id}:result",
                3600,
                json.dumps({'error': {'error_message': friendly_error}, 'history_id': history_id})
            )

            logger.info(f"[轮询] task_id={task_id}, 已标记为 failed")
            return {'status': 'failed', 'error': {'error_message': friendly_error}, 'history_id': history_id}

        else:
            logger.info(f"[轮询] task_id={task_id}, Ark 状态仍为 {remote_status}, 等待下次轮询")

    except Exception as e:
        logger.error(f'[轮询] task_id={task_id}, 查询 Ark 状态失败: {e}', exc_info=True)

    return None


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

    logger.info(f"[任务查询] task_id={task_id}, status={status}")

    # 如果任务失败，打印错误原因
    if status == 'failed':
        result_json = client.get(f"task:{task_id}:result")
        if result_json:
            try:
                result_data = json.loads(result_json)
                error = result_data.get('error', {})
                error_msg = error.get('error_message', '未知错误')
                logger.error(f"[任务查询] task_id={task_id}, 失败原因: {error_msg}")
            except Exception as e:
                logger.error(f"[任务查询] task_id={task_id}, 解析失败结果出错: {e}")

    # 如果任务正在处理中且有 remote_id，主动轮询上游状态
    if status == 'processing':
        remote_id = client.get(f"task:{task_id}:remote_id")
        is_downloading = client.get(f"task:{task_id}:downloading")

        if remote_id and not is_downloading:
            provider = client.get(f"task:{task_id}:provider")
            logger.info(f"[任务查询] task_id={task_id}, 检测到 remote_id={remote_id}, provider={provider}, 开始轮询")

            if provider == 'ark':
                api_key = client.get(f"task:{task_id}:api_key")
                base_url = client.get(f"task:{task_id}:base_url")
                user_id = client.get(f"task:{task_id}:user_id")

                poll_result = await _poll_ark_task(task_id, remote_id, api_key, base_url, user_id)
                if poll_result:
                    return poll_result

        return {'status': 'processing'}

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
