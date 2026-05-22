import logging
import pathlib
from aiohttp import web
from server import PromptServer

from . import config as cfg
from .repositories import provider_repo
from .task_routes import task_routes as _  # noqa: F401 触发 task 路由注册

routes = PromptServer.instance.routes
logger = logging.getLogger('comfy_api_proxy')

OUTPUT_DIR = cfg.get_output_dir()

# 兼容旧代码：__init__.py 通过 routes.REDIS_AVAILABLE 判断是否启动 worker
from .services import task_queue as _tq
_tq.get_client()  # 触发连接，初始化 AVAILABLE
REDIS_AVAILABLE = _tq.AVAILABLE


# ── CORS 中间件 ────────────────────────────────────────────────────────────

@web.middleware
async def cors_middleware(request, handler):
    if request.method == 'OPTIONS':
        response = web.Response()
    else:
        response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

PromptServer.instance.app.middlewares.append(cors_middleware)


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
    try:
        pid = request.rel_url.query.get('provider_id')
        model_type = request.rel_url.query.get('type')
        models = provider_repo.get_all_models(provider_id=int(pid) if pid else None)
        if model_type:
            models = [m for m in models if m.get('type') == model_type]
        return web.json_response({'models': models})
    except Exception as e:
        logger.error(f'[api-proxy] get_models error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/providers ──────────────────────────────────────────────────

@routes.get('/api-proxy/providers')
async def get_providers(request: web.Request):
    try:
        providers = provider_repo.get_all_providers()
        return web.json_response({'providers': providers})
    except Exception as e:
        logger.error(f'[api-proxy] get_providers error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/providers/{provider_id}/models')
async def get_provider_models(request: web.Request):
    provider_id = request.match_info['provider_id']
    try:
        models = provider_repo.get_all_models(provider_id=int(provider_id))
        return web.json_response({'models': models})
    except Exception as e:
        logger.error(f'[api-proxy] get_provider_models error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/output/{filename} ─────────────────────────────────────────

@routes.get('/api-proxy/output/{filename}')
async def serve_output_file(request: web.Request):
    filename = request.match_info['filename']
    if '..' in filename or '/' in filename or '\\' in filename:
        raise web.HTTPBadRequest(reason='Invalid filename')
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise web.HTTPNotFound()
    return web.FileResponse(file_path)


# ── /api-proxy/input/{filename} ──────────────────────────────────────────

@routes.get('/api-proxy/input/{filename}')
async def serve_input_file(request: web.Request):
    filename = request.match_info['filename']
    if '..' in filename or '/' in filename or '\\' in filename:
        raise web.HTTPBadRequest(reason='Invalid filename')
    file_path = cfg.get_input_dir() / filename
    if not file_path.exists():
        raise web.HTTPNotFound()
    return web.FileResponse(file_path)


# ── /api-proxy/user/assets ────────────────────────────────────────────────

@routes.get('/api-proxy/user/assets')
async def get_user_assets(request: web.Request):
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    try:
        user_id = int(user_id)
    except ValueError:
        raise web.HTTPBadRequest(reason='user_id must be an integer')

    asset_type = request.rel_url.query.get('asset_type')
    try:
        from .repositories import asset_repo
        assets = asset_repo.get_user_assets(user_id, asset_type)
        return web.json_response({'assets': assets})
    except Exception as e:
        logger.error(f'[api-proxy] get_user_assets error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/upload/image ───────────────────────────────────────────────

@routes.post('/api-proxy/upload/image')
async def upload_input_image(request: web.Request):
    import uuid
    from .repositories import asset_repo

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

    input_dir = cfg.get_input_dir()
    ext = pathlib.Path(filename).suffix or '.png'
    unique_filename = f'{uuid.uuid4().hex}{ext}'
    location = str(input_dir / unique_filename)

    with open(location, 'wb') as f:
        f.write(file_bytes)

    try:
        asset_id = asset_repo.save_input_asset(user_id, unique_filename, location)
    except Exception as e:
        logger.error(f'[api-proxy] upload_input_image db error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))

    logger.info(f'[api-proxy] uploaded input image: id={asset_id} location={location}')
    return web.json_response({'id': asset_id, 'location': location})


@routes.get('/api-proxy/upload/image/{asset_id}/b64')
async def get_input_image_b64(request: web.Request):
    import base64
    from .repositories import asset_repo

    asset_id = int(request.match_info['asset_id'])
    asset = asset_repo.get_input_asset(asset_id)
    if not asset:
        raise web.HTTPNotFound(reason=f'input asset {asset_id} not found')

    file_path = pathlib.Path(asset['location'])
    if not file_path.exists():
        raise web.HTTPNotFound(reason=f'file not found: {asset["location"]}')

    b64 = base64.b64encode(file_path.read_bytes()).decode()
    return web.json_response({'b64': b64, 'location': asset['location']})


# ── /api-proxy/history ────────────────────────────────────────────────────

@routes.post('/api-proxy/history')
async def save_history(request: web.Request):
    from .repositories import history_repo, asset_repo
    body = await request.json()
    user_id = body.get('user_id')
    prompt = body.get('prompt', '')
    output_urls = body.get('output_urls', [])
    input_asset_ids = body.get('input_asset_ids', [])
    task_id = body.get('task_id')
    mode = body.get('mode')
    status = body.get('status', 'done')
    type_ = body.get('type')
    message = body.get('message')
    model_id = body.get('model_id')

    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')

    output_asset_ids = []
    for url in output_urls:
        filename = pathlib.Path(url).name
        row = asset_repo.find_asset_by_filename(filename, int(user_id))
        if row:
            output_asset_ids.append(row['id'])

    try:
        history_id = history_repo.save_history(
            user_id=int(user_id),
            prompt=prompt,
            input_asset_ids=input_asset_ids,
            output_asset_ids=output_asset_ids,
            task_id=task_id,
            mode=mode,
            status=status,
            type_=type_,
            message=message,
            model_id=model_id,
        )
        return web.json_response({'id': history_id})
    except Exception as e:
        logger.error(f'[api-proxy] save_history error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/history')
async def get_history(request: web.Request):
    from .repositories import history_repo
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    type_filter = request.rel_url.query.get('type')
    try:
        records = history_repo.get_user_history(int(user_id), type_filter=type_filter or None)
        return web.json_response({'records': records})
    except Exception as e:
        logger.error(f'[api-proxy] get_history error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.delete('/api-proxy/history/{history_id}')
async def delete_history(request: web.Request):
    from .repositories import history_repo
    history_id = request.match_info['history_id']
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    try:
        deleted = history_repo.delete_history(int(history_id), int(user_id))
        return web.json_response({'ok': deleted})
    except Exception as e:
        logger.error(f'[api-proxy] delete_history error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.delete('/api-proxy/history')
async def clear_history(request: web.Request):
    from .repositories import history_repo
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    try:
        count = history_repo.clear_user_history(int(user_id))
        return web.json_response({'deleted': count})
    except Exception as e:
        logger.error(f'[api-proxy] clear_history error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/test/save-asset ────────────────────────────────────────────

@routes.post('/api-proxy/test/save-asset')
async def test_save_asset(request: web.Request):
    from .repositories import asset_repo
    body = await request.json()
    user_id = body.get('user_id', 1)
    location = body.get('location', 'test.png')
    asset_type = body.get('asset_type', 'picture')
    try:
        asset_repo.save_output_asset(location, user_id, asset_type)
        logger.info(f'[test] saved: user_id={user_id}, location={location}, type={asset_type}')
        return web.json_response({'ok': True, 'message': 'Asset saved'})
    except Exception as e:
        logger.error(f'[test] save failed: {e}')
        raise web.HTTPInternalServerError(reason=str(e))

