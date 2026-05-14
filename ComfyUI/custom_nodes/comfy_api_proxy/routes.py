import re
import logging
import aiohttp
import asyncio
from concurrent.futures import ThreadPoolExecutor
from aiohttp import web
from server import PromptServer

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from . import config as cfg

routes = PromptServer.instance.routes
logger = logging.getLogger('comfy_api_proxy')

# CORS 中间件
@web.middleware
async def cors_middleware(request, handler):
    if request.method == 'OPTIONS':
        # 处理预检请求
        response = web.Response()
    else:
        response = await handler(request)

    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

# 注册中间件
PromptServer.instance.app.middlewares.append(cors_middleware)

# 线程池用于运行同步的 Gemini SDK
_executor = ThreadPoolExecutor(max_workers=4)

# 输出目录
import pathlib
OUTPUT_DIR = pathlib.Path(r'D:\AAAA\output')

# Redis 连接（任务队列 + 状态存储）
import redis
import uuid
import json as json_lib
try:
    redis_client = redis.Redis(**cfg.get_redis_config())
    redis_client.ping()
    REDIS_AVAILABLE = True
    logger.info('[api-proxy] Redis connected')
except Exception as e:
    REDIS_AVAILABLE = False
    logger.warning(f'[api-proxy] Redis not available: {e}')


# ── 工具函数 ───────────────────────────────────────────────────────────────

def _get_provider_by_model(model_id: int) -> int | None:
    """根据模型表的主键 id 从数据库查找对应的 rfid (provider_id)"""
    try:
        from . import db_queries
        model = db_queries.get_model_by_id(model_id)
        if model:
            return model.get('rfid')
    except Exception:
        pass
    return None


def _check_config(provider_id: int | None = None, model_id: int | None = None):
    """
    检查 API_KEY / BASE_URL 是否已配置
    优先从数据库获取提供商配置，如果没有则回退到 .env 文件

    参数:
        provider_id: 直接指定提供商 ID
        model_id: 通过模型 ID 自动查找提供商
    """
    # 如果提供了 model_id，先查找对应的 provider_id
    if model_id and not provider_id:
        provider_id = _get_provider_by_model(model_id)
        if not provider_id:
            logger.warning(f'[api-proxy] Model "{model_id}" not found in database, using default provider')

    # 如果指定了 provider_id，从数据库获取
    if provider_id:
        result = cfg.get_provider_config_by_id(str(provider_id))
        if not result:
            raise web.HTTPNotFound(reason=f'provider "{provider_id}" not found')
        return result  # 返回 (api_key, base_url)

    # 尝试从数据库获取默认提供商
    default_provider = cfg.get_default_provider_config()
    if default_provider:
        return default_provider['api_key'], default_provider['base_url']

    # 回退到 .env 文件
    api_key  = cfg.get_api_key()
    base_url = cfg.get_base_url()
    if not api_key:
        raise web.HTTPServiceUnavailable(reason='API_KEY not configured')
    if not base_url:
        raise web.HTTPServiceUnavailable(reason='BASE_URL not configured')
    return api_key, base_url


def _detect_model_provider(model: str) -> str:
    """
    根据模型名称判断供应商
    返回: 'openai' | 'gemini' | 'generic'
    """
    model_lower = model.lower()

    # OpenAI 模型（仅 DALL-E 系列走 OpenAI images API）
    if any(x in model_lower for x in ['gpt', 'dalle','mcs7c']):
        return 'openai'

    # Gemini 模型（仅 generateContent 接口，不含 Veo）
    if 'gemini' in model_lower:
        return 'gemini'

    # 其他模型使用通用异步 API
    return 'generic'


def _extract_image_from_markdown(content: str) -> str | None:
    """
    从 Markdown 格式中提取图片 data URI
    例：![image](data:image/jpeg;base64,...) → data:image/jpeg;base64,...
    """
    match = re.search(r'!\[.*?\]\((data:image/[^)]+)\)', content)
    if match:
        return match.group(1)
    return None


def _extract_video_url(content: str) -> str | None:
    """
    从返回内容中提取视频 URL，支持两种格式：
    1. <video controls>\\n    https://...\\n</video>
    2. [Download Video](https://...)
    """
    # 优先从 <video> 标签里取
    match = re.search(r'<video[^>]*>\s*(https?://\S+)\s*</video>', content)
    if match:
        return match.group(1).strip()
    # 再从 Markdown 链接取
    match = re.search(r'\[Download Video\]\((https?://[^)]+)\)', content)
    if match:
        return match.group(1).strip()
    return None


# ── /api-proxy/config ─────────────────────────────────────────────────────

@routes.get('/api-proxy/config')
async def get_config(request: web.Request):
    return web.json_response({
        'base_url': cfg.get_base_url(),
        'has_key': bool(cfg.get_api_key()),
    })


@routes.put('/api-proxy/config')
async def put_config(request: web.Request):
    body = await request.json()
    cfg.save_env(body.get('api_key'), body.get('base_url'))
    return web.json_response({'ok': True})


# ── /api-proxy/models ─────────────────────────────────────────────────────

@routes.get('/api-proxy/models')
async def get_models(request: web.Request):
    """获取所有模型列表"""
    from . import db_queries
    try:
        provider_id = request.rel_url.query.get('provider_id')
        model_type = request.rel_url.query.get('type')  # 'image' 或 'video'

        models = db_queries.get_all_models(provider_id=int(provider_id) if provider_id else None)

        # 根据 type 参数过滤
        if model_type:
            models = [m for m in models if m.get('type') == model_type]

        return web.json_response({'models': models})
    except Exception as e:
        logger.error(f'[api-proxy] get_models error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/providers ──────────────────────────────────────────────────

@routes.get('/api-proxy/providers')
async def get_providers(request: web.Request):
    """获取所有提供商列表"""
    from . import db_queries
    try:
        providers = db_queries.get_all_providers()
        return web.json_response({'providers': providers})
    except Exception as e:
        logger.error(f'[api-proxy] get_providers error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/providers/{provider_id}/models')
async def get_provider_models(request: web.Request):
    """获取指定提供商的模型列表"""
    from . import db_queries
    provider_id = request.match_info['provider_id']

    try:
        models = db_queries.get_all_models(provider_id=int(provider_id))
        return web.json_response({'models': models})
    except Exception as e:
        logger.error(f'[api-proxy] get_provider_models error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))

    """更新提供商"""


# ── /api-proxy/txt2img ────────────────────────────────────────────────────
# 文生图（根据模型类型使用不同的 SDK）
#
# 请求 (JSON):
#   model   string  必填
#   prompt  string  必填
#   width   int     可选
#   height  int     可选
#   n       int     可选，默认 1
#
# 返回: { "images": [ {"url": "..."} ] } 或 { "task_id": "xxx" }

@routes.post('/api-proxy/txt2img')
async def txt2img(request: web.Request):
    body = await request.json()

    model           = body.get('model')  # 模型表的主键 ID
    prompt          = body.get('prompt', '').strip()
    width           = body.get('width')
    height          = body.get('height')
    n               = body.get('n', 1)
    input_asset_ids = body.get('input_asset_ids', [])
    user_id         = body.get('user_id')

    if not model:
        raise web.HTTPBadRequest(reason='model is required')
    if not prompt:
        raise web.HTTPBadRequest(reason='prompt is required')

    # 根据 model_id 自动获取提供商配置（也支持手动指定 provider_id）
    provider_id = body.get('provider_id')
    api_key, base_url = _check_config(provider_id=provider_id, model_id=model)

    # 从数据库获取模型信息（获取实际的模型名称）
    from . import db_queries
    model_info = db_queries.get_model_by_id(model)
    if not model_info:
        raise web.HTTPNotFound(reason=f'model {model} not found')
    model_name = model_info['name']

    # 查库读多个文件转 base64
    image_b64_list = []
    if input_asset_ids:
        import pymysql
        import base64
        import pathlib
        try:
            conn = pymysql.connect(**cfg.get_db_config())
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                for asset_id in input_asset_ids:
                    cursor.execute('SELECT location FROM input_assets WHERE id = %s', (asset_id,))
                    row = cursor.fetchone()
                    if not row:
                        raise web.HTTPNotFound(reason=f'input asset {asset_id} not found')
                    file_path = pathlib.Path(row['location'])
                    if not file_path.exists():
                        raise web.HTTPNotFound(reason=f'file not found: {row["location"]}')
                    image_b64_list.append(base64.b64encode(file_path.read_bytes()).decode())
            conn.close()
        except web.HTTPException:
            raise
        except Exception as e:
            raise web.HTTPInternalServerError(reason=str(e))
        logger.info(f'[api-proxy] img2img {len(image_b64_list)} image(s) loaded')

    # 兼容旧的单图字段
    image_b64 = image_b64_list[0] if image_b64_list else None

    provider = _detect_model_provider(model_name)
    logger.info(f'[api-proxy] 文生图、图生图 model={model_name} provider={provider} prompt={prompt[:50]}')

    # ── OpenAI SDK ──
    if provider == 'openai':
        if not OPENAI_AVAILABLE:
            raise web.HTTPServiceUnavailable(reason='OpenAI SDK not installed')
        if not REDIS_AVAILABLE:
            raise web.HTTPServiceUnavailable(reason='Redis not available, cannot queue OpenAI tasks')

        # 检查队列长度，防止内存爆掉
        queue_length = redis_client.llen('queue:txt2img')
        if queue_length >= 20:
            raise web.HTTPServiceUnavailable(reason=f'系统繁忙，当前排队 {queue_length} 个任务，请稍后再试')

        # 生成 task_id，提交到 Redis 队列
        task_id = str(uuid.uuid4())
        task_payload = {
            'task_id': task_id,
            'provider': 'openai',
            'model': model_name,
            'prompt': prompt,
            'width': width,
            'height': height,
            'n': n,
            'user_id': user_id,
            'api_key': api_key,
            'base_url': base_url,
            'image_b64_list': image_b64_list,  # 支持图生图
        }

        redis_client.lpush('queue:txt2img', json_lib.dumps(task_payload))
        redis_client.setex(f'task:{task_id}:status', 3600, 'pending')
        redis_client.setex(f'task:{task_id}:created_at', 3600, str(asyncio.get_event_loop().time()))

        logger.info(f'[api-proxy] openai task queued: {task_id}')
        return web.json_response({'task_id': task_id})

    # ── Gemini SDK ──
    elif provider == 'gemini':
        if not GEMINI_AVAILABLE:
            raise web.HTTPServiceUnavailable(reason='Gemini SDK not installed')
        if not REDIS_AVAILABLE:
            raise web.HTTPServiceUnavailable(reason='Redis not available, cannot queue Gemini tasks')

        # 检查队列长度，防止内存爆掉
        queue_length = redis_client.llen('queue:txt2img')
        if queue_length >= 20:
            raise web.HTTPServiceUnavailable(reason=f'系统繁忙，当前排队 {queue_length} 个任务，请稍后再试')

        # 生成 task_id，提交到 Redis 队列
        task_id = str(uuid.uuid4())
        task_payload = {
            'task_id': task_id,
            'provider': 'gemini',
            'model': model_name,
            'prompt': prompt,
            'user_id': user_id,
            'api_key': api_key,
            'base_url': base_url,
            'image_b64_list': image_b64_list,
        }

        redis_client.lpush('queue:txt2img', json_lib.dumps(task_payload))
        redis_client.setex(f'task:{task_id}:status', 3600, 'pending')
        redis_client.setex(f'task:{task_id}:created_at', 3600, str(asyncio.get_event_loop().time()))

        logger.info(f'[api-proxy] gemini task queued: {task_id}')
        return web.json_response({'task_id': task_id})

    # 不支持的提供商
    else:
        raise web.HTTPBadRequest(reason=f'Unsupported provider: {provider}')


# ── /api-proxy/txt2video ──────────────────────────────────────────────────
# 文生视频（根据模型类型使用不同的 SDK）
#
# 请求 (JSON):
#   model   string  必填
#   prompt  string  必填
#
# 返回: { "video_url": "xxx" } 或 { "task_id": "xxx" }

@routes.post('/api-proxy/txt2video')
async def txt2video(request: web.Request):
    body = await request.json()

    model  = body.get('model')  # 模型表的主键 ID
    prompt = body.get('prompt', '').strip()

    if not model:
        raise web.HTTPBadRequest(reason='model is required')
    if not prompt:
        raise web.HTTPBadRequest(reason='prompt is required')

    # 根据 model_id 自动获取提供商配置（也支持手动指定 provider_id）
    provider_id = body.get('provider_id')
    api_key, base_url = _check_config(provider_id=provider_id, model_id=model)

    # 从数据库获取模型信息（获取实际的模型名称）
    from . import db_queries
    model_info = db_queries.get_model_by_id(model)
    if not model_info:
        raise web.HTTPNotFound(reason=f'model {model} not found')
    model_name = model_info['name']

    provider = _detect_model_provider(model_name)
    logger.info(f'[api-proxy] txt2video model={model_name} provider={provider} prompt={prompt[:50]}')

    # ── 使用 Ark SDK (通过 OpenAI 兼容接口) ──
    if not REDIS_AVAILABLE:
        raise web.HTTPServiceUnavailable(reason='Redis not available, cannot queue video tasks')

    # 检查队列长度
    queue_length = redis_client.llen('queue:txt2video')
    if queue_length >= 20:
        raise web.HTTPServiceUnavailable(reason=f'系统繁忙，当前排队 {queue_length} 个任务，请稍后再试')

    # 生成 task_id，提交到 Redis 队列
    task_id = str(uuid.uuid4())
    user_id = body.get('user_id')
    ratio = body.get('ratio', '16:9')
    resolution = body.get('resolution', '720p')
    duration = body.get('duration', 8)

    task_payload = {
        'task_id': task_id,
        'provider': 'ark',
        'model': model_name,
        'prompt': prompt,
        'ratio': ratio,
        'resolution': resolution,
        'duration': duration,
        'user_id': user_id,
        'api_key': api_key,
        'base_url': base_url,
    }

    redis_client.lpush('queue:txt2video', json_lib.dumps(task_payload))
    redis_client.setex(f'task:{task_id}:status', 3600, 'pending')
    redis_client.setex(f'task:{task_id}:created_at', 3600, str(asyncio.get_event_loop().time()))

    logger.info(f'[api-proxy] txt2video task queued: {task_id}')
    return web.json_response({'task_id': task_id})


# ── /api-proxy/img2video ──────────────────────────────────────────────────
# 图生视频 / 视频生视频（使用火山引擎 Ark SDK）
#
# 请求 (JSON):
#   model   string  必填，模型 ID
#   prompt  string  必填，提示词
#   input_asset_ids  array  可选，资产 ID 列表（图片或视频）
#   input_file  file  可选，上传的文件
#   user_id  int  可选
#   ratio  string  可选，默认 16:9
#   resolution  string  可选，默认 720p
#   duration  int  可选，默认 8
#
# 返回: { "task_id": "xxx" }

@routes.post('/api-proxy/img2video')
async def img2video(request: web.Request):
    # 检查 Content-Type
    content_type = request.headers.get('Content-Type', '')
    logger.info(f'[api-proxy] img2video Content-Type: {content_type}')

    if not content_type.startswith('multipart/form-data'):
        raise web.HTTPBadRequest(reason='Content-Type must be multipart/form-data')

    # 使用 multipart reader（最原始的方式）
    body = {}
    input_files = []

    try:
        reader = await request.multipart()

        async for part in reader:
            if part.filename:
                # 文件字段
                file_data = await part.read(decode=False)
                input_files.append({
                    'filename': part.filename,
                    'data': file_data,
                    'content_type': part.headers.get('Content-Type', 'application/octet-stream')
                })
                logger.info(f'[api-proxy] Received file: {part.filename}, size: {len(file_data)} bytes')
            else:
                # 普通字段
                value = await part.read(decode=True)
                # 确保转换为字符串
                if isinstance(value, bytes):
                    body[part.name] = value.decode('utf-8')
                elif isinstance(value, bytearray):
                    body[part.name] = value.decode('utf-8')
                else:
                    body[part.name] = str(value)
                logger.info(f'[api-proxy] Received field: {part.name}')

        logger.info(f'[api-proxy] Successfully parsed multipart data')
    except Exception as e:
        logger.error(f'[api-proxy] Error parsing multipart data: {e}')
        # 如果第一次失败，等待一下再试一次
        await asyncio.sleep(0.1)
        try:
            # 重新创建 reader
            reader = await request.multipart()
            async for part in reader:
                if part.filename:
                    file_data = await part.read(decode=False)
                    input_files.append({
                        'filename': part.filename,
                        'data': file_data,
                        'content_type': part.headers.get('Content-Type', 'application/octet-stream')
                    })
                else:
                    value = await part.read(decode=True)
                    # 确保转换为字符串
                    if isinstance(value, bytes):
                        body[part.name] = value.decode('utf-8')
                    elif isinstance(value, bytearray):
                        body[part.name] = value.decode('utf-8')
                    else:
                        body[part.name] = str(value)
            logger.info(f'[api-proxy] Retry succeeded')
        except Exception as e2:
            logger.error(f'[api-proxy] Retry also failed: {e2}')
            raise web.HTTPBadRequest(reason=f'Error reading form data: {e2}')

    logger.info(f'[api-proxy] img2video body: {body}')
    logger.info(f'[api-proxy] img2video files count: {len(input_files)}')

    model = body.get('model')
    prompt = body.get('prompt', '').strip()

    if not model:
        raise web.HTTPBadRequest(reason='model is required')
    if not prompt:
        raise web.HTTPBadRequest(reason='prompt is required')

    # 根据 model_id 自动获取提供商配置
    provider_id = body.get('provider_id')
    api_key, base_url = _check_config(provider_id=provider_id, model_id=model)

    # 从数据库获取模型信息
    from . import db_queries
    model_info = db_queries.get_model_by_id(model)
    if not model_info:
        raise web.HTTPNotFound(reason=f'model {model} not found')
    model_name = model_info['name']

    logger.info(f'[api-proxy] img2video model={model_name} prompt={prompt[:50]}')

    if not REDIS_AVAILABLE:
        raise web.HTTPServiceUnavailable(reason='Redis not available, cannot queue video tasks')

    # 检查队列长度
    queue_length = redis_client.llen('queue:img2video')
    if queue_length >= 20:
        raise web.HTTPServiceUnavailable(reason=f'系统繁忙，当前排队 {queue_length} 个任务，请稍后再试')

    # 生成 task_id，提交到 Redis 队列
    task_id = str(uuid.uuid4())
    user_id = body.get('user_id')
    ratio = body.get('ratio', '16:9')
    resolution = body.get('resolution', '720p')
    duration = int(body.get('duration', 8))

    # 处理输入资产
    input_asset_ids = body.get('input_asset_ids', '')
    if input_asset_ids:
        input_asset_ids = [int(x.strip()) for x in input_asset_ids.split(',') if x.strip()]
    else:
        input_asset_ids = []

    task_payload = {
        'task_id': task_id,
        'provider': 'ark',
        'model': model_name,
        'prompt': prompt,
        'ratio': ratio,
        'resolution': resolution,
        'duration': duration,
        'user_id': user_id,
        'api_key': api_key,
        'base_url': base_url,
        'input_asset_ids': input_asset_ids,
        'input_files': [{'filename': f['filename'], 'data': f['data'].hex(), 'content_type': f['content_type']} for f in input_files],
    }

    redis_client.lpush('queue:img2video', json_lib.dumps(task_payload))
    redis_client.setex(f'task:{task_id}:status', 3600, 'pending')
    redis_client.setex(f'task:{task_id}:created_at', 3600, str(asyncio.get_event_loop().time()))

    logger.info(f'[api-proxy] img2video task queued: {task_id}, files: {len(input_files)}')
    return web.json_response({'task_id': task_id})


# ── 下载远程资源并保存到本地，写入 assets 表 ─────────────────────────────────

async def _download_and_save_asset(remote_url: str, user_id, ext: str) -> str | None:
    """下载远程 URL，保存到 OUTPUT_DIR，写入 assets 表，返回 ComfyUI view URL"""
    import uuid, pymysql
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = f'{uuid.uuid4().hex}.{ext}'
        save_path = OUTPUT_DIR / filename

        async with aiohttp.ClientSession() as session:
            async with session.get(remote_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    logger.error(f'[api-proxy] download failed {resp.status}: {remote_url}')
                    return None
                save_path.write_bytes(await resp.read())

        location = str(save_path)
        # 判断资产类型
        asset_type = 'video' if ext.lower() in ['mp4', 'mov', 'avi', 'webm'] else 'picture'

        if user_id:
            try:
                conn = pymysql.connect(**cfg.get_db_config())
                with conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            'INSERT INTO assets (location, rfid, asset_type, created_at) VALUES (%s, %s, %s, NOW())',
                            (location, int(user_id), asset_type)
                        )
                    conn.commit()
                logger.info(f'[api-proxy] saved asset: {location} user={user_id} type={asset_type}')
            except Exception as e:
                logger.error(f'[api-proxy] db insert failed: {e}')

        # 返回前端可访问的 URL
        return f'/api/api-proxy/output/{filename}'
    except Exception as e:
        logger.error(f'[api-proxy] _download_and_save_asset error: {e}')
        return None


# ── /api-proxy/task/{task_id} ─────────────────────────────────────────────
# 查询异步任务状态
#
# 返回: { "status": "in_progress|completed|failed", "result": {...} }

@routes.get('/api-proxy/task/{task_id}')
async def get_task_status(request: web.Request):
    task_id = request.match_info['task_id']
    user_id = request.rel_url.query.get('user_id')

    # 优先从 Redis 查询（Gemini/OpenAI 任务）
    if REDIS_AVAILABLE:
        status = redis_client.get(f'task:{task_id}:status')
        if status:
            logger.info(f'[api-proxy] 任务id {task_id} Redis的小状态: {status}')

            # 如果是 processing 状态，检查是否有 remote_id（Seedance/Ark 任务）
            if status == 'processing':
                remote_id = redis_client.get(f'task:{task_id}:remote_id')
                if remote_id:
                    # 检查是否正在下载（防止并发下载）
                    downloading_lock = redis_client.get(f'task:{task_id}:downloading')
                    if downloading_lock:
                        logger.info(f'[{task_id}] Video is being downloaded by another request')
                        return web.json_response({'status': 'processing'})

                    # 获取任务提供商
                    provider = redis_client.get(f'task:{task_id}:provider')
                    api_key = redis_client.get(f'task:{task_id}:api_key')
                    stored_user_id = redis_client.get(f'task:{task_id}:user_id')

                    # Ark 任务（文生视频 / 图生视频）
                    if provider == 'ark':
                        try:
                            # 判断是使用 OpenAI 兼容接口还是 Ark SDK
                            base_url = redis_client.get(f'task:{task_id}:base_url')

                            # 如果有 base_url，使用 OpenAI 兼容接口（文生视频）
                            if base_url:
                                from openai import OpenAI
                                import uuid, pymysql

                                client = OpenAI(api_key=api_key, base_url=base_url)
                                result = client.get(f"/contents/generations/tasks/{remote_id}", cast_to=object)

                                remote_status = result.get("status")
                                logger.info(f'[{task_id}] Ark (OpenAI API) status: {remote_status}')

                                if remote_status == "succeeded":
                                    video_url = result.get("content", {}).get("video_url")
                                    if not video_url:
                                        raise Exception('No video URL in result')

                                    logger.info(f'[{task_id}] Ark completed, downloading video from {video_url}')

                                    # 设置下载锁（20分钟超时）
                                    redis_client.setex(f'task:{task_id}:downloading', 1200, '1')

                                    try:
                                        # 同步下载视频
                                        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                                        filename = f'{uuid.uuid4().hex}.mp4'
                                        save_path = OUTPUT_DIR / filename

                                        async with aiohttp.ClientSession() as session:
                                            async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=600)) as resp:
                                                if resp.status != 200:
                                                    raise Exception(f'Failed to download video: {resp.status}')
                                                with open(save_path, 'wb') as f:
                                                    f.write(await resp.read())

                                        local_url = f'/api/api-proxy/output/{filename}'
                                        logger.info(f'[{task_id}] Video saved to {save_path}')

                                        # 写入 assets 表
                                        if stored_user_id:
                                            try:
                                                conn = pymysql.connect(**cfg.get_db_config())
                                                with conn:
                                                    with conn.cursor() as cursor:
                                                        cursor.execute(
                                                            'INSERT INTO assets (location, rfid, asset_type, created_at) VALUES (%s, %s, %s, NOW())',
                                                            (str(save_path), int(stored_user_id), 'video')
                                                        )
                                                    conn.commit()
                                                logger.info(f'[{task_id}] Saved to assets table as video')
                                            except Exception as db_e:
                                                logger.error(f'[{task_id}] DB insert failed: {db_e}')

                                        # 更新 Redis 状态为完成
                                        redis_client.set(f'task:{task_id}:status', 'completed')
                                        redis_client.setex(f'task:{task_id}:result', 3600, json_lib.dumps({
                                            'result': [{'url': local_url, 'type': 'video'}]
                                        }))

                                        # 清理临时数据
                                        redis_client.delete(f'task:{task_id}:remote_id')
                                        redis_client.delete(f'task:{task_id}:api_key')
                                        redis_client.delete(f'task:{task_id}:base_url')
                                        redis_client.delete(f'task:{task_id}:provider')
                                        redis_client.delete(f'task:{task_id}:user_id')
                                        redis_client.delete(f'task:{task_id}:downloading')

                                        return web.json_response({
                                            'status': 'completed',
                                            'result': [{'url': local_url, 'type': 'video'}]
                                        })
                                    except Exception as download_error:
                                        redis_client.delete(f'task:{task_id}:downloading')
                                        raise download_error

                                elif remote_status == "failed":
                                    error_msg = result.get("error", {}).get("message", "Video generation failed")
                                    redis_client.set(f'task:{task_id}:status', 'failed')
                                    redis_client.setex(f'task:{task_id}:result', 3600, json_lib.dumps({
                                        'error': {'error_message': error_msg}
                                    }))
                                    return web.json_response({
                                        'status': 'failed',
                                        'error': {'error_message': error_msg}
                                    })

                            # 否则使用 Ark SDK（图生视频）
                            else:
                                from volcenginesdkarkruntime import Ark
                                import uuid, pymysql

                                client = Ark(api_key=api_key)
                                result = client.content_generation.tasks.get(task_id=remote_id)

                                remote_status = result.status
                                logger.info(f'[{task_id}] Ark SDK status: {remote_status}')

                                if remote_status == "succeeded":
                                    # 获取视频 URL
                                    video_url = result.content.video_url if hasattr(result.content, 'video_url') else None
                                    if not video_url:
                                        raise Exception('No video URL in result')

                                    logger.info(f'[{task_id}] Ark completed, downloading video from {video_url}')

                                    # 设置下载锁（20分钟超时）
                                    redis_client.setex(f'task:{task_id}:downloading', 1200, '1')

                                    try:
                                        # 同步下载视频
                                        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                                        filename = f'{uuid.uuid4().hex}.mp4'
                                        save_path = OUTPUT_DIR / filename

                                        async with aiohttp.ClientSession() as session:
                                            async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=600)) as resp:
                                                if resp.status != 200:
                                                    raise Exception(f'Failed to download video: {resp.status}')
                                                with open(save_path, 'wb') as f:
                                                    f.write(await resp.read())

                                        local_url = f'/api/api-proxy/output/{filename}'
                                        logger.info(f'[{task_id}] Video saved to {save_path}')

                                        # 写入 assets 表
                                        if stored_user_id:
                                            try:
                                                conn = pymysql.connect(**cfg.get_db_config())
                                                with conn:
                                                    with conn.cursor() as cursor:
                                                        cursor.execute(
                                                            'INSERT INTO assets (location, rfid, asset_type, created_at) VALUES (%s, %s, %s, NOW())',
                                                            (str(save_path), int(stored_user_id), 'video')
                                                        )
                                                    conn.commit()
                                                logger.info(f'[{task_id}] Saved to assets table as video')
                                            except Exception as db_e:
                                                logger.error(f'[{task_id}] DB insert failed: {db_e}')

                                        # 更新 Redis 状态为完成
                                        redis_client.set(f'task:{task_id}:status', 'completed')
                                        redis_client.setex(f'task:{task_id}:result', 3600, json_lib.dumps({
                                            'result': [{'url': local_url, 'type': 'video'}]
                                        }))

                                        # 清理临时数据
                                        redis_client.delete(f'task:{task_id}:remote_id')
                                        redis_client.delete(f'task:{task_id}:api_key')
                                        redis_client.delete(f'task:{task_id}:provider')
                                        redis_client.delete(f'task:{task_id}:user_id')
                                        redis_client.delete(f'task:{task_id}:downloading')

                                        return web.json_response({
                                            'status': 'completed',
                                            'result': [{'url': local_url, 'type': 'video'}]
                                        })
                                    except Exception as download_error:
                                        redis_client.delete(f'task:{task_id}:downloading')
                                        raise download_error

                                elif remote_status == "failed":
                                    error_msg = result.error.message if hasattr(result, 'error') and hasattr(result.error, 'message') else "Video generation failed"
                                    redis_client.set(f'task:{task_id}:status', 'failed')
                                    redis_client.setex(f'task:{task_id}:result', 3600, json_lib.dumps({
                                        'error': {'error_message': error_msg}
                                    }))
                                    return web.json_response({
                                        'status': 'failed',
                                        'error': {'error_message': error_msg}
                                    })

                        except Exception as e:
                            logger.error(f'[{task_id}] Error querying Ark: {e}')
                            # 继续返回 processing 状态，下次再试

                    # 其他提供商（保留兼容性）
                    else:
                        base_url = redis_client.get(f'task:{task_id}:base_url')
                        if api_key and base_url:
                            try:
                                from openai import OpenAI
                                import uuid, pymysql, requests

                                client = OpenAI(api_key=api_key, base_url=base_url)
                                result = client.get(f"/contents/generations/tasks/{remote_id}", cast_to=object)

                                remote_status = result.get("status")
                                logger.info(f'[{task_id}] Seedance status: {remote_status}')

                                if remote_status == "succeeded":
                                    # 获取视频 URL
                                    video_url = result.get("content", {}).get("video_url")
                                    if not video_url:
                                        raise Exception('No video URL in result')

                                    logger.info(f'[{task_id}] Seedance completed, downloading video from {video_url}')

                                    # 设置下载锁（20分钟超时）
                                    redis_client.setex(f'task:{task_id}:downloading', 1200, '1')

                                    try:
                                        # 同步下载视频（等待完成）
                                        import uuid, pymysql, requests
                                        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                                        filename = f'{uuid.uuid4().hex}.mp4'
                                        save_path = OUTPUT_DIR / filename

                                        # 下载视频
                                        async with aiohttp.ClientSession() as session:
                                            async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=600)) as resp:
                                                if resp.status != 200:
                                                    raise Exception(f'Failed to download video: {resp.status}')
                                                with open(save_path, 'wb') as f:
                                                    f.write(await resp.read())

                                        local_url = f'/api/api-proxy/output/{filename}'
                                        logger.info(f'[{task_id}] Video saved to {save_path}')

                                        # 写入 assets 表
                                        if stored_user_id:
                                            try:
                                                conn = pymysql.connect(**cfg.get_db_config())
                                                with conn:
                                                    with conn.cursor() as cursor:
                                                        cursor.execute(
                                                            'INSERT INTO assets (location, rfid, asset_type, created_at) VALUES (%s, %s, %s, NOW())',
                                                            (str(save_path), int(stored_user_id), 'video')
                                                        )
                                                    conn.commit()
                                                logger.info(f'[{task_id}] Saved to assets table as video')
                                            except Exception as db_e:
                                                logger.error(f'[{task_id}] DB insert failed: {db_e}')

                                        # 更新 Redis 状态为完成（使用本地 URL）
                                        redis_client.set(f'task:{task_id}:status', 'completed')
                                        redis_client.setex(f'task:{task_id}:result', 3600, json_lib.dumps({
                                            'result': [{'url': local_url, 'type': 'video'}]
                                        }))

                                        # 清理临时数据
                                        redis_client.delete(f'task:{task_id}:remote_id')
                                        redis_client.delete(f'task:{task_id}:api_key')
                                        redis_client.delete(f'task:{task_id}:base_url')
                                        redis_client.delete(f'task:{task_id}:user_id')
                                        redis_client.delete(f'task:{task_id}:downloading')

                                        return web.json_response({
                                            'status': 'completed',
                                            'result': [{'url': local_url, 'type': 'video'}]
                                        })
                                    except Exception as download_error:
                                        # 下载失败，释放锁
                                        redis_client.delete(f'task:{task_id}:downloading')
                                        raise download_error

                                elif remote_status == "failed":
                                    error_msg = result.get("error", {}).get("message", "Video generation failed")
                                    redis_client.set(f'task:{task_id}:status', 'failed')
                                    redis_client.setex(f'task:{task_id}:result', 3600, json_lib.dumps({
                                        'error': {'error_message': error_msg}
                                    }))
                                    return web.json_response({
                                        'status': 'failed',
                                        'error': {'error_message': error_msg}
                                    })

                            except Exception as e:
                                logger.error(f'[{task_id}] Error querying Seedance: {e}')
                                # 继续返回 processing 状态，下次再试

            # 返回当前状态
            response = {'status': status}

            if status in ['completed', 'failed']:
                result_json = redis_client.get(f'task:{task_id}:result')
                if result_json:
                    result_data = json_lib.loads(result_json)
                    if status == 'completed':
                        response['result'] = result_data.get('result', [])
                    else:
                        response['error'] = result_data.get('error')

            return web.json_response(response)

    # 任务不存在
    raise web.HTTPNotFound(reason=f'Task {task_id} not found or expired. Tasks expire after 48 hours.')


# ── /api-proxy/task/{task_id}/cancel ──────────────────────────────────────
# 取消任务

@routes.post('/api-proxy/task/{task_id}/cancel')
async def cancel_task(request: web.Request):
    task_id = request.match_info['task_id']

    if not REDIS_AVAILABLE:
        raise web.HTTPServiceUnavailable(reason='Redis not available')

    try:
        # 更新任务状态为 failed
        redis_client.set(f'task:{task_id}:status', 'failed')
        redis_client.setex(f'task:{task_id}:result', 3600, json_lib.dumps({
            'error': {'error_message': '任务已被用户取消'}
        }))

        logger.info(f'[api-proxy] Task {task_id} cancelled by user')
        return web.json_response({'ok': True})
    except Exception as e:
        logger.error(f'[api-proxy] Cancel task error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/task/{task_id}/priority ────────────────────────────────────
# 任务插队

@routes.post('/api-proxy/task/{task_id}/priority')
async def prioritize_task(request: web.Request):
    task_id = request.match_info['task_id']

    if not REDIS_AVAILABLE:
        raise web.HTTPServiceUnavailable(reason='Redis not available')

    try:
        # 检查任务状态
        status = redis_client.get(f'task:{task_id}:status')
        if not status:
            raise web.HTTPNotFound(reason='Task not found')

        if status != 'pending':
            raise web.HTTPBadRequest(reason=f'Task is {status}, cannot prioritize')

        # 从队列中找到任务并移到队首
        # 先确定任务在哪个队列
        provider = redis_client.get(f'task:{task_id}:provider')

        if provider == 'ark':
            # 检查是文生视频还是图生视频
            remote_id = redis_client.get(f'task:{task_id}:remote_id')
            if remote_id:
                queue_name = 'queue:img2video'
            else:
                queue_name = 'queue:txt2video'
        else:
            queue_name = 'queue:txt2img'

        # 从队列中找到任务
        queue_length = redis_client.llen(queue_name)
        found = False

        for i in range(queue_length):
            task_json = redis_client.lindex(queue_name, i)
            if task_json:
                task_data = json_lib.loads(task_json)
                if task_data.get('task_id') == task_id:
                    # 找到了，移除并插入到队首
                    redis_client.lrem(queue_name, 1, task_json)
                    redis_client.rpush(queue_name, task_json)
                    found = True
                    logger.info(f'[api-proxy] Task {task_id} prioritized in {queue_name}')
                    break

        if not found:
            raise web.HTTPNotFound(reason='Task not found in queue')

        return web.json_response({'ok': True})
    except web.HTTPException:
        raise
    except Exception as e:
        logger.error(f'[api-proxy] Prioritize task error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/output/{filename} ─────────────────────────────────────────
# 提供 D:\AAAA\output 目录下文件的访问

@routes.get('/api-proxy/output/{filename}')
async def serve_output_file(request: web.Request):
    filename = request.match_info['filename']
    # 防止路径穿越
    if '..' in filename or '/' in filename or '\\' in filename:
        raise web.HTTPBadRequest(reason='Invalid filename')
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise web.HTTPNotFound()
    return web.FileResponse(file_path)


# ── /api-proxy/user/assets ────────────────────────────────────────────────
# 查询用户的图片资产列表
#
# 请求参数:
#   user_id  int  必填，用户 ID
#
# 返回: { "assets": [ {"id": 1, "location": "ComfyUI_00001_.png"}, ... ] }

@routes.get('/api-proxy/user/assets')
async def get_user_assets(request: web.Request):
    import pymysql

    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')

    try:
        user_id = int(user_id)
    except ValueError:
        raise web.HTTPBadRequest(reason='user_id must be an integer')

    asset_type = request.rel_url.query.get('asset_type')  # 'picture' | 'video' | None

    try:
        conn = pymysql.connect(**cfg.get_db_config())
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if asset_type in ('picture', 'video'):
                cursor.execute(
                    'SELECT id, location, asset_type FROM assets WHERE rfid = %s AND asset_type = %s ORDER BY id DESC',
                    (user_id, asset_type)
                )
            else:
                cursor.execute(
                    'SELECT id, location, asset_type FROM assets WHERE rfid = %s ORDER BY id DESC',
                    (user_id,)
                )
            assets = cursor.fetchall()
        conn.close()

        return web.json_response({'assets': assets})

    except Exception as e:
        logger.error(f'[api-proxy] get_user_assets error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/test/save-asset ────────────────────────────────────────────
# 测试接口：手动保存资产
@routes.post('/api-proxy/test/save-asset')
async def test_save_asset(request: web.Request):
    import pymysql
    body = await request.json()
    user_id = body.get('user_id', 1)
    location = body.get('location', 'test.png')
    asset_type = body.get('asset_type', 'picture')

    try:
        conn = pymysql.connect(**cfg.get_db_config())
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assets (location, rfid, asset_type, created_at) VALUES (%s, %s, %s, NOW())",
                (location, user_id, asset_type)
            )
            conn.commit()
        conn.close()
        logger.info(f'[test] saved: user_id={user_id}, location={location}, type={asset_type}')
        return web.json_response({'ok': True, 'message': 'Asset saved'})
    except Exception as e:
        logger.error(f'[test] save failed: {e}')
        raise web.HTTPInternalServerError(reason=str(e))

# ── /api-proxy/upload/image ───────────────────────────────────────────────
# 上传输入图片，保存到 ComfyUI input 目录，写入 input_assets 表
#
# 请求: multipart/form-data
#   file     File  必填
#   user_id  int   必填
#
# 返回: { "id": 1, "location": "xxx.png" }

@routes.post('/api-proxy/upload/image')
async def upload_input_image(request: web.Request):
    import pymysql
    import uuid
    import pathlib

    reader = await request.multipart()
    user_id = None
    file_bytes = None
    filename = None

    async for field in reader:
        if field.name == 'user_id':
            user_id = int(await field.read())
        elif field.name == 'file':
            filename = field.filename or 'upload.png'
            file_bytes = await field.read()

    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    if not file_bytes:
        raise web.HTTPBadRequest(reason='file is required')

    # 生成唯一文件名，保存到 D:\AAAA\input
    import pathlib
    import uuid
    ext = pathlib.Path(filename).suffix or '.png'
    unique_name = f'input_{uuid.uuid4().hex}{ext}'
    input_dir = pathlib.Path(r'D:\AAAA\input')
    input_dir.mkdir(parents=True, exist_ok=True)
    save_path = input_dir / unique_name
    save_path.write_bytes(file_bytes)
    location = str(save_path)  # 绝对路径

    # 写入数据库
    try:
        conn = pymysql.connect(**cfg.get_db_config())
        with conn.cursor() as cursor:
            cursor.execute(
                'INSERT INTO input_assets (rfid, filename, location) VALUES (%s, %s, %s)',
                (user_id, filename, location)
            )
            conn.commit()
            asset_id = cursor.lastrowid
        conn.close()
    except Exception as e:
        logger.error(f'[api-proxy] upload_input_image db error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))

    logger.info(f'[api-proxy] uploaded input image: id={asset_id} location={location}')
    return web.json_response({'id': asset_id, 'location': location})


# ── /api-proxy/upload/image/{asset_id}/b64 ───────────────────────────────
# 查库取路径，读文件返回 base64（供图生图使用）

@routes.get('/api-proxy/upload/image/{asset_id}/b64')
async def get_input_image_b64(request: web.Request):
    import pymysql
    import base64
    import pathlib

    asset_id = request.match_info['asset_id']
    try:
        conn = pymysql.connect(**cfg.get_db_config())
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute('SELECT location FROM input_assets WHERE id = %s', (asset_id,))
            row = cursor.fetchone()
        conn.close()
    except Exception as e:
        raise web.HTTPInternalServerError(reason=str(e))

    if not row:
        raise web.HTTPNotFound(reason=f'input asset {asset_id} not found')

    import pathlib
    file_path = pathlib.Path(row['location'])
    if not file_path.exists():
        raise web.HTTPNotFound(reason=f'file not found: {row["location"]}')

    b64 = base64.b64encode(file_path.read_bytes()).decode()
    return web.json_response({'b64': b64, 'location': row['location']})
