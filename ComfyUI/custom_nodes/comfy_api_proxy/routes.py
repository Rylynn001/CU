import logging
import pathlib
from aiohttp import web
from server import PromptServer

from . import config as cfg
from .repositories import provider_repo
from .task_routes import task_routes as _  # noqa: F401 触发 task 路由注册
from .task_routes import drama_routes as _drama_routes  # noqa: F401 触发 drama 路由注册
from .ai import routes as _agent_routes  # noqa: F401 触发 agent 路由注册

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
        logger.error(f'[api-proxy] 获取模型列表失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/providers ──────────────────────────────────────────────────

@routes.get('/api-proxy/providers')
async def get_providers(request: web.Request):
    try:
        providers = provider_repo.get_all_providers()
        return web.json_response({'providers': providers})
    except Exception as e:
        logger.error(f'[api-proxy] 获取提供商列表失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/providers/{provider_id}/models')
async def get_provider_models(request: web.Request):
    provider_id = request.match_info['provider_id']
    try:
        models = provider_repo.get_all_models(provider_id=int(provider_id))
        return web.json_response({'models': models})
    except Exception as e:
        logger.error(f'[api-proxy] 获取提供商模型失败: {e}')
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
    tag_str = request.rel_url.query.get('tag')
    tag = int(tag_str) if tag_str is not None else None
    favorite_only = request.rel_url.query.get('favorite') == '1'
    try:
        page = int(request.rel_url.query.get('page', 1))
    except ValueError:
        page = 1
    try:
        from .repositories import asset_repo
        assets, total = asset_repo.get_user_assets(
            user_id, asset_type, tag, favorite_only, page=page, page_size=30
        )
        return web.json_response({'assets': assets, 'total': total, 'page': page, 'page_size': 30})
    except Exception as e:
        logger.error(f'[api-proxy] 获取用户资产失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/user/assets/{asset_id}/favorite ───────────────────────────

@routes.post('/api-proxy/user/assets/{asset_id}/favorite')
async def set_asset_favorite(request: web.Request):
    asset_id = request.match_info['asset_id']
    try:
        asset_id = int(asset_id)
    except ValueError:
        raise web.HTTPBadRequest(reason='asset_id must be an integer')

    body = await request.json()
    user_id = body.get('user_id')
    tag = body.get('tag', 1)

    if user_id is None:
        raise web.HTTPBadRequest(reason='user_id is required')
    try:
        user_id = int(user_id)
        tag = int(tag)
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(reason='参数类型错误')
    if tag not in (0, 1, 2, 3, 4):
        raise web.HTTPBadRequest(reason='tag 必须是 0-4')

    try:
        from .repositories import asset_repo
        ok = asset_repo.set_asset_tag(asset_id, user_id, tag)
        if not ok:
            raise web.HTTPNotFound(reason='资产不存在或无权限')
        return web.json_response({'ok': True})
    except web.HTTPException:
        raise
    except Exception as e:
        logger.error(f'[api-proxy] 设置收藏失败: {e}')
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

    output_dir = cfg.get_output_dir()
    ext = pathlib.Path(filename).suffix or '.png'
    unique_filename = f'{uuid.uuid4().hex}{ext}'
    location = str(output_dir / unique_filename)

    with open(location, 'wb') as f:
        f.write(file_bytes)

    try:
        asset_id = asset_repo.save_output_asset(location, user_id, 'picture')
    except Exception as e:
        logger.error(f'[api-proxy] 上传输入图片数据库错误: {e}')
        raise web.HTTPInternalServerError(reason=str(e))

    logger.info(f'[api-proxy] 输入图片已上传: id={asset_id} location={location}')
    return web.json_response({'id': asset_id, 'location': location})


@routes.get('/api-proxy/upload/image/{asset_id}/b64')
async def get_input_image_b64(request: web.Request):
    import base64
    from .repositories import asset_repo

    asset_id = int(request.match_info['asset_id'])
    asset = asset_repo.get_asset_by_id(asset_id)
    if not asset:
        raise web.HTTPNotFound(reason=f'asset {asset_id} not found')

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
        logger.error(f'[api-proxy] 保存历史记录失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/history')
async def get_history(request: web.Request):
    from .repositories import history_repo
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    type_filter = request.rel_url.query.get('type')
    try:
        page = int(request.rel_url.query.get('page', 1))
        page_size = int(request.rel_url.query.get('page_size', 30))
    except ValueError:
        raise web.HTTPBadRequest(reason='page 和 page_size 必须为整数')
    if page_size not in (30, 50, 100):
        page_size = 30
    try:
        records, total = history_repo.get_user_history(
            int(user_id), type_filter=type_filter or None, page=page, page_size=page_size
        )
        return web.json_response({'records': records, 'total': total, 'page': page, 'page_size': page_size})
    except Exception as e:
        logger.error(f'[api-proxy] 获取历史记录失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/history/by-asset/{asset_id} ────────────────────────────────

@routes.get('/api-proxy/history/by-asset/{asset_id}')
async def get_history_by_asset(request: web.Request):
    from .repositories import history_repo
    asset_id = request.match_info['asset_id']
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    try:
        record = history_repo.find_history_by_asset_id(int(user_id), int(asset_id))
    except ValueError:
        raise web.HTTPBadRequest(reason='asset_id 和 user_id 必须为整数')
    if not record:
        raise web.HTTPNotFound(reason='未找到该资产对应的历史记录')
    return web.json_response({'record': record})


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
        logger.error(f'[api-proxy] 删除历史记录失败: {e}')
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
        logger.error(f'[api-proxy] 清空历史记录失败: {e}')
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
        logger.info(f'[test] 已保存: user_id={user_id}, location={location}, type={asset_type}')
        return web.json_response({'ok': True, 'message': 'Asset saved'})
    except Exception as e:
        logger.error(f'[test] 保存失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/extract-frame ──────────────────────────────────────────────

@routes.post('/api-proxy/extract-frame')
async def extract_frame(request: web.Request):
    import asyncio
    import uuid
    import subprocess
    from .repositories import asset_repo

    body = await request.json()
    asset_id = body.get('asset_id')
    time_sec = body.get('time_sec')
    user_id = body.get('user_id')

    if asset_id is None or time_sec is None or user_id is None:
        raise web.HTTPBadRequest(reason='asset_id, time_sec, user_id are required')

    try:
        asset_id = int(asset_id)
        time_sec = float(time_sec)
        user_id = int(user_id)
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(reason='参数类型错误')

    asset = asset_repo.get_asset_by_id(asset_id)
    if not asset:
        raise web.HTTPNotFound(reason='资产不存在')

    # location 可能是相对路径或绝对路径，统一解析到 OUTPUT_DIR
    location = asset['location']
    video_path = pathlib.Path(location)
    if not video_path.is_absolute():
        video_path = OUTPUT_DIR / video_path.name

    if not video_path.exists():
        raise web.HTTPNotFound(reason='视频文件不存在')

    out_filename = f'frame_{uuid.uuid4().hex[:12]}.png'
    out_path = OUTPUT_DIR / out_filename

    cmd = [
        'ffmpeg', '-y',
        '-ss', str(time_sec),
        '-i', str(video_path),
        '-frames:v', '1',
        str(out_path),
    ]

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, check=True, capture_output=True)
        )
    except subprocess.CalledProcessError as e:
        logger.error(f'[extract-frame] ffmpeg 失败: {e.stderr.decode(errors="ignore")}')
        raise web.HTTPInternalServerError(reason='ffmpeg 抽帧失败')

    new_id = asset_repo.save_output_asset(str(out_path), user_id, 'picture')
    logger.info(f'[extract-frame] 抽帧成功: asset_id={new_id}, file={out_filename}')
    return web.json_response({'ok': True, 'asset_id': new_id, 'filename': out_filename})


# ── /api-proxy/assets/by-ids ──────────────────────────────────────────────

@routes.post('/api-proxy/assets/by-ids')
async def get_assets_by_ids(request: web.Request):
    from .repositories import asset_repo
    body = await request.json()
    ids = body.get('ids', [])
    if not isinstance(ids, list):
        raise web.HTTPBadRequest(reason='ids must be a list')
    try:
        assets = asset_repo.get_assets_by_ids([int(i) for i in ids])
        return web.json_response({'assets': assets})
    except Exception as e:
        logger.error(f'[api-proxy] 按 id 查询资产失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


# ── /api-proxy/projects ───────────────────────────────────────────────────

@routes.get('/api-proxy/projects')
async def get_projects(request: web.Request):
    from .repositories import asset_repo
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    try:
        user_id = int(user_id)
    except ValueError:
        raise web.HTTPBadRequest(reason='user_id must be an integer')
    try:
        projects = asset_repo.get_user_projects(user_id)
        return web.json_response({'projects': projects})
    except Exception as e:
        logger.error(f'[api-proxy] 获取项目失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/projects/{project_id}')
async def get_project_detail(request: web.Request):
    from .repositories import asset_repo
    project_id = int(request.match_info['project_id'])
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    detail = asset_repo.get_project_detail(project_id, int(user_id))
    if detail is None:
        raise web.HTTPForbidden(reason='非项目成员或项目不存在')
    return web.json_response(detail)


@routes.get('/api-proxy/projects/{project_id}/categories')
async def get_project_categories(request: web.Request):
    from .repositories import asset_repo
    project_id = int(request.match_info['project_id'])
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    categories = asset_repo.get_project_categories(project_id, int(user_id))
    if categories is None:
        raise web.HTTPForbidden(reason='非项目成员')
    return web.json_response({'categories': categories})


@routes.post('/api-proxy/projects')
async def create_project(request: web.Request):
    from .repositories import asset_repo
    body = await request.json()
    user_id = body.get('user_id')
    name = body.get('name')
    if not user_id or not name:
        raise web.HTTPBadRequest(reason='user_id and name are required')
    try:
        result = asset_repo.create_project(name, int(user_id))
        return web.json_response({
            'id': result['id'],
            'name': name,
            'role': 'owner',
            'categories': result['categories'],
        })
    except Exception as e:
        logger.error(f'[api-proxy] 创建项目失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.delete('/api-proxy/projects/{project_id}')
async def delete_project(request: web.Request):
    from .repositories import asset_repo
    project_id = int(request.match_info['project_id'])
    body = await request.json()
    user_id = body.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    ok = asset_repo.delete_project(project_id, int(user_id))
    if not ok:
        raise web.HTTPNotFound(reason='项目不存在或无权限')
    return web.json_response({'ok': True})


@routes.put('/api-proxy/projects/{project_id}')
async def rename_project(request: web.Request):
    from .repositories import asset_repo
    project_id = int(request.match_info['project_id'])
    body = await request.json()
    user_id = body.get('user_id')
    name = body.get('name', '').strip()
    if not user_id or not name:
        raise web.HTTPBadRequest(reason='user_id and name are required')
    ok = asset_repo.rename_project(project_id, int(user_id), name)
    if not ok:
        raise web.HTTPNotFound(reason='项目不存在或无权限')
    return web.json_response({'ok': True})


# ── /api-proxy/categories ─────────────────────────────────────────────────

@routes.post('/api-proxy/categories')
async def create_category(request: web.Request):
    from .repositories import asset_repo
    body = await request.json()
    project_id = body.get('project_id')
    name = body.get('name')
    if not project_id or not name:
        raise web.HTTPBadRequest(reason='project_id and name are required')
    try:
        cat_id = asset_repo.create_category(int(project_id), name)
        return web.json_response({'id': cat_id, 'name': name})
    except Exception as e:
        logger.error(f'[api-proxy] 创建分类失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.delete('/api-proxy/categories/{category_id}')
async def delete_category(request: web.Request):
    from .repositories import asset_repo
    category_id = int(request.match_info['category_id'])
    ok = asset_repo.delete_category(category_id)
    if not ok:
        raise web.HTTPNotFound(reason='分类不存在')
    return web.json_response({'ok': True})


@routes.put('/api-proxy/categories/{category_id}')
async def rename_category(request: web.Request):
    from .repositories import asset_repo
    category_id = int(request.match_info['category_id'])
    body = await request.json()
    name = body.get('name', '').strip()
    if not name:
        raise web.HTTPBadRequest(reason='name is required')
    ok = asset_repo.rename_category(category_id, name)
    if not ok:
        raise web.HTTPNotFound(reason='分类不存在')
    return web.json_response({'ok': True})


# ── /api-proxy/categories/{category_id}/assets ───────────────────────────

@routes.get('/api-proxy/categories/{category_id}/assets')
async def get_category_assets(request: web.Request):
    from .repositories import asset_repo
    category_id = int(request.match_info['category_id'])
    try:
        assets = asset_repo.get_category_assets(category_id)
        return web.json_response({'assets': assets})
    except Exception as e:
        logger.error(f'[api-proxy] 获取分类资产失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.post('/api-proxy/categories/{category_id}/assets')
async def add_asset_to_category(request: web.Request):
    from .repositories import asset_repo
    category_id = int(request.match_info['category_id'])
    body = await request.json()
    asset_id = body.get('asset_id')
    user_id = body.get('user_id')
    resubmit_id = body.get('resubmit_id')  # 续接被驳回的提交记录（重新提交时传）
    if asset_id is None or user_id is None:
        raise web.HTTPBadRequest(reason='asset_id and user_id are required')
    try:
        review_status = asset_repo.add_asset_to_category(
            category_id, int(asset_id), int(user_id),
            resubmit_id=int(resubmit_id) if resubmit_id is not None else None
        )
        if review_status is None:
            raise web.HTTPForbidden(reason='非项目成员或无权续接该提交记录')
        return web.json_response({'ok': True, 'review_status': review_status})
    except web.HTTPException:
        raise
    except Exception as e:
        logger.error(f'[api-proxy] 添加资产到分类失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.delete('/api-proxy/categories/{category_id}/assets/{asset_id}')
async def remove_asset_from_category(request: web.Request):
    from .repositories import asset_repo
    category_id = int(request.match_info['category_id'])
    asset_id = int(request.match_info['asset_id'])
    ok = asset_repo.remove_asset_from_category(category_id, asset_id)
    if not ok:
        raise web.HTTPNotFound(reason='关联不存在')
    return web.json_response({'ok': True})


# ── /api-proxy/projects/{project_id}/members ──────────────────────────────

@routes.get('/api-proxy/projects/{project_id}/members')
async def list_project_members(request: web.Request):
    from .repositories import member_repo
    project_id = int(request.match_info['project_id'])
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    # 仅项目成员可查看成员列表
    if member_repo.get_member_role(project_id, int(user_id)) is None:
        raise web.HTTPForbidden(reason='无权限')
    members = member_repo.list_members(project_id)
    return web.json_response({'members': members})


@routes.get('/api-proxy/projects/{project_id}/candidate-users')
async def list_candidate_users(request: web.Request):
    from .repositories import member_repo
    project_id = int(request.match_info['project_id'])
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    # 仅 owner/admin 可拉人，故也仅他们可查候选用户
    if member_repo.get_member_role(project_id, int(user_id)) not in ('owner', 'admin'):
        raise web.HTTPForbidden(reason='无权限')

    # 获取分页和搜索参数
    keyword = request.rel_url.query.get('keyword', '')
    try:
        page = max(1, int(request.rel_url.query.get('page', 1)))
        page_size = min(100, max(1, int(request.rel_url.query.get('page_size', 50))))
    except ValueError:
        raise web.HTTPBadRequest(reason='page 和 page_size 必须为整数')

    users, total = member_repo.list_candidate_users(project_id, keyword, page, page_size)
    return web.json_response({'users': users, 'total': total, 'page': page, 'page_size': page_size})


@routes.post('/api-proxy/projects/{project_id}/members')
async def add_project_member(request: web.Request):
    from .repositories import member_repo
    project_id = int(request.match_info['project_id'])
    body = await request.json()
    user_id = body.get('user_id')
    username = (body.get('username') or '').strip()
    role = body.get('role', 'member')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    if role not in ('admin', 'member'):
        raise web.HTTPBadRequest(reason='role 只能是 admin 或 member')
    # 仅 owner/admin 可拉人
    if member_repo.get_member_role(project_id, int(user_id)) not in ('owner', 'admin'):
        raise web.HTTPForbidden(reason='无权限')
    if not username:
        raise web.HTTPBadRequest(reason='username is required')
    target = member_repo.find_user_by_name(username)
    if not target:
        raise web.HTTPNotFound(reason='用户不存在')
    member_repo.add_member(project_id, target['id'], role)
    return web.json_response({'ok': True, 'user_id': target['id'], 'username': target['user_name'], 'role': role})


@routes.put('/api-proxy/projects/{project_id}/members/{member_user_id}')
async def set_project_member_role(request: web.Request):
    from .repositories import member_repo
    project_id = int(request.match_info['project_id'])
    member_user_id = int(request.match_info['member_user_id'])
    body = await request.json()
    user_id = body.get('user_id')
    role = body.get('role')
    if not user_id or role not in ('admin', 'member'):
        raise web.HTTPBadRequest(reason='user_id 和合法的 role 必填')
    # 仅 owner/admin 可改角色，且不能改 owner
    if member_repo.get_member_role(project_id, int(user_id)) not in ('owner', 'admin'):
        raise web.HTTPForbidden(reason='无权限')
    if member_repo.get_member_role(project_id, member_user_id) == 'owner':
        raise web.HTTPBadRequest(reason='不能修改 owner 角色')
    ok = member_repo.set_member_role(project_id, member_user_id, role)
    if not ok:
        raise web.HTTPNotFound(reason='成员不存在')
    return web.json_response({'ok': True})


@routes.delete('/api-proxy/projects/{project_id}/members/{member_user_id}')
async def remove_project_member(request: web.Request):
    from .repositories import member_repo
    project_id = int(request.match_info['project_id'])
    member_user_id = int(request.match_info['member_user_id'])
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    # 仅 owner/admin 可移除，且不能移除 owner
    if member_repo.get_member_role(project_id, int(user_id)) not in ('owner', 'admin'):
        raise web.HTTPForbidden(reason='无权限')
    if member_repo.get_member_role(project_id, member_user_id) == 'owner':
        raise web.HTTPBadRequest(reason='不能移除 owner')
    ok = member_repo.remove_member(project_id, member_user_id)
    if not ok:
        raise web.HTTPNotFound(reason='成员不存在')
    return web.json_response({'ok': True})


# ── /api-proxy/pending-assets ─────────────────────────────────────────────

@routes.get('/api-proxy/pending-assets')
async def list_pending_assets(request: web.Request):
    from .repositories import asset_repo
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    try:
        page = max(1, int(request.rel_url.query.get('page', 1)))
        page_size = min(100, max(1, int(request.rel_url.query.get('page_size', 50))))
    except ValueError:
        raise web.HTTPBadRequest(reason='page 和 page_size 必须为整数')
    assets, total = asset_repo.list_pending_assets(int(user_id), page, page_size)
    return web.json_response({
        'assets': assets, 'total': total, 'page': page, 'page_size': page_size
    })


@routes.post('/api-proxy/categories/{category_id}/assets/{asset_id}/review')
async def review_category_asset(request: web.Request):
    from .repositories import asset_repo
    category_id = int(request.match_info['category_id'])
    asset_id = int(request.match_info['asset_id'])
    body = await request.json()
    user_id = body.get('user_id')
    approve = body.get('approve')
    comment = (body.get('comment') or '').strip() or None
    if not user_id or approve is None:
        raise web.HTTPBadRequest(reason='user_id 和 approve 必填')
    ok = asset_repo.review_asset(category_id, asset_id, int(user_id), bool(approve), comment)
    if not ok:
        raise web.HTTPForbidden(reason='无权限或该素材不在待审核状态')
    return web.json_response({'ok': True})


@routes.get('/api-proxy/categories/{category_id}/assets/{asset_id}/reviews')
async def get_asset_review_timeline(request: web.Request):
    from .repositories import asset_repo
    category_id = int(request.match_info['category_id'])
    asset_id = int(request.match_info['asset_id'])
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    result = asset_repo.get_asset_review_timeline(category_id, asset_id, int(user_id))
    if result is None:
        raise web.HTTPForbidden(reason='无权限查看')
    return web.json_response(result)


@routes.get('/api-proxy/my-submissions')
async def list_my_submissions(request: web.Request):
    from .repositories import asset_repo
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    try:
        page = max(1, int(request.rel_url.query.get('page', 1)))
        page_size = min(100, max(1, int(request.rel_url.query.get('page_size', 50))))
    except ValueError:
        raise web.HTTPBadRequest(reason='page 和 page_size 必须为整数')
    subs, total, rejected_total = asset_repo.list_my_submissions(int(user_id), page, page_size)
    return web.json_response({
        'submissions': subs,
        'total': total,
        'rejected_total': rejected_total,
        'page': page,
        'page_size': page_size,
    })


# ── /api-proxy/node-boards ────────────────────────────────────────────────

@routes.get('/api-proxy/node-boards')
async def list_node_boards(request: web.Request):
    from .repositories import board_repo
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    try:
        boards = board_repo.list_boards(int(user_id))
        return web.json_response({'boards': boards})
    except Exception as e:
        logger.error(f'[node-board] 获取工作区列表失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.post('/api-proxy/node-boards')
async def create_node_board(request: web.Request):
    from .repositories import board_repo
    body = await request.json()
    user_id = body.get('user_id')
    name = (body.get('name') or '').strip() or '新工作区'
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    try:
        board = board_repo.create_board(int(user_id), name)
        return web.json_response(board)
    except Exception as e:
        logger.error(f'[node-board] 创建工作区失败: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/node-boards/{board_id}')
async def get_node_board(request: web.Request):
    from .repositories import board_repo
    board_id = int(request.match_info['board_id'])
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    board = board_repo.get_board(board_id, int(user_id))
    if not board:
        raise web.HTTPNotFound(reason='工作区不存在')
    return web.json_response(board)


@routes.put('/api-proxy/node-boards/{board_id}')
async def save_node_board(request: web.Request):
    from .repositories import board_repo
    board_id = int(request.match_info['board_id'])
    body = await request.json()
    user_id = body.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    panels = body.get('panels', [{}, {}, {}])
    while len(panels) < 3:
        panels.append({})
    ok = board_repo.save_board(
        board_id, int(user_id),
        panels[0].get('asset_ids', []),
        panels[1].get('asset_ids', []),
        panels[2].get('asset_ids', []),
        body.get('panel2_image_history_ids', []),
        body.get('panel2_video_history_ids', []),
    )
    if not ok:
        raise web.HTTPNotFound(reason='工作区不存在或无权限')
    return web.json_response({'ok': True})


@routes.patch('/api-proxy/node-boards/{board_id}')
async def rename_node_board(request: web.Request):
    from .repositories import board_repo
    board_id = int(request.match_info['board_id'])
    body = await request.json()
    user_id = body.get('user_id')
    name = (body.get('name') or '').strip()
    if not user_id or not name:
        raise web.HTTPBadRequest(reason='user_id and name are required')
    ok = board_repo.rename_board(board_id, int(user_id), name)
    if not ok:
        raise web.HTTPNotFound(reason='工作区不存在或无权限')
    return web.json_response({'ok': True})


@routes.delete('/api-proxy/node-boards/{board_id}')
async def delete_node_board(request: web.Request):
    from .repositories import board_repo
    board_id = int(request.match_info['board_id'])
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        raise web.HTTPBadRequest(reason='user_id is required')
    ok = board_repo.delete_board(board_id, int(user_id))
    if not ok:
        raise web.HTTPNotFound(reason='工作区不存在或无权限')
    return web.json_response({'ok': True})


# ── /api-proxy/gecko/init ─────────────────────────────────────────────────

@routes.post('/api-proxy/gecko/init')
async def gecko_init(request: web.Request):
    from .utils.http_client import post
    from requests.exceptions import RequestException

    try:
        result = post('https://192.168.0.25/api/python-v2/init')
        message = result.get('message', '')
        data = result.get('data')

        return web.json_response({
            'success': message == '成功',
            'message': message,
            'username': data if isinstance(data, str) else None
        })
    except RequestException as e:
        logger.error(f'[gecko] 初始化失败: {e}')
        return web.json_response({
            'success': False,
            'message': '请先登录Gecko'
        }, status=200)
    except Exception as e:
        logger.error(f'[gecko] 初始化异常: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


