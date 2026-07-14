import pathlib
import shutil
import tempfile
import zipfile
from aiohttp import web
from server import PromptServer
from . import config as cfg
from .repositories import usd_repo
from .services import usd_service

routes = PromptServer.instance.routes
USD_ROOT = cfg.get_output_dir() / 'usd'
USD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED = {'.usd', '.usda', '.usdc', '.usdz', '.zip', '.png', '.jpg', '.jpeg', '.exr', '.avif'}

def _owner(request):
    value = request.rel_url.query.get('user_id')
    if not value: raise web.HTTPBadRequest(reason='user_id is required')
    return int(value)

def _stage(request):
    stage = usd_repo.get_stage(int(request.match_info['stage_id']), _owner(request))
    if not stage: raise web.HTTPNotFound(reason='USD stage not found')
    return stage

def _safe_extract(archive, destination):
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target = (destination / member.filename).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve(): raise web.HTTPBadRequest(reason='unsafe archive path')
            if pathlib.Path(member.filename).suffix.lower() not in ALLOWED and not member.is_dir(): raise web.HTTPBadRequest(reason=f'unsupported archive file: {member.filename}')
        package.extractall(destination)

@routes.get('/api-proxy/usd/capabilities')
async def usd_capabilities(_request):
    return web.json_response({'openusd': usd_service.OPENUSD_AVAILABLE, 'formats': ['usd','usda','usdc','usdz']})

@routes.post('/api-proxy/usd/stages')
async def create_usd_stage(request):
    if not usd_service.OPENUSD_AVAILABLE: raise web.HTTPServiceUnavailable(reason='OpenUSD runtime unavailable')
    reader = await request.multipart(); fields = {}; uploads = []
    temp_dir = pathlib.Path(tempfile.mkdtemp(prefix='usd-', dir=USD_ROOT))
    try:
        async for field in reader:
            if field.filename:
                filename = pathlib.Path(field.filename).name
                if pathlib.Path(filename).suffix.lower() not in ALLOWED: raise web.HTTPBadRequest(reason='unsupported file type')
                path = temp_dir / filename; size = 0
                with path.open('wb') as output:
                    while chunk := await field.read_chunk():
                        size += len(chunk)
                        if size > 512*1024*1024: raise web.HTTPRequestEntityTooLarge(max_size=512*1024*1024, actual_size=size)
                        output.write(chunk)
                uploads.append(path)
            else: fields[field.name] = await field.text()
        user_id, project_id = int(fields.get('user_id', 0)), int(fields.get('project_id', 0))
        if not user_id or not project_id or not usd_repo.project_owned(project_id, user_id): raise web.HTTPForbidden(reason='project not found')
        for archive in [p for p in uploads if p.suffix.lower() == '.zip']:
            _safe_extract(archive, temp_dir); archive.unlink()
        candidates = [p for p in temp_dir.rglob('*') if p.suffix.lower() in {'.usd','.usda','.usdc','.usdz'}]
        root_name = pathlib.Path(fields.get('root_file', '')).name
        root = next((p for p in candidates if p.name == root_name), candidates[0] if len(candidates) == 1 else None)
        if not root: raise web.HTTPBadRequest(reason='root_file is required for multi-file stages')
        usd_service.describe_stage(str(root))
        stage_id = usd_repo.create_stage(user_id, project_id, fields.get('name') or root.stem, str(root))
        final_dir = USD_ROOT / str(user_id) / str(stage_id); final_dir.parent.mkdir(parents=True, exist_ok=True)
        relative = root.relative_to(temp_dir); shutil.move(str(temp_dir), str(final_dir))
        final_root = final_dir / relative; session = final_dir / 'session.usda'
        usd_repo.update_paths(stage_id, str(final_root), str(session))
        usd_service.export_preview(str(final_root), str(final_dir / 'preview.usdc'))
        return web.json_response({'id': stage_id, 'name': fields.get('name') or root.stem}, status=201)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True); raise

@routes.get('/api-proxy/usd/stages')
async def list_usd_stages(request):
    return web.json_response({'stages': usd_repo.list_stages(_owner(request), int(request.rel_url.query.get('project_id', 0)))})

@routes.get('/api-proxy/usd/stages/{stage_id}')
async def get_usd_stage(request):
    stage = _stage(request)
    try: metadata = usd_service.describe_stage(stage['root_path'], stage.get('session_path'))
    except Exception as error: raise web.HTTPUnprocessableEntity(reason=str(error))
    return web.json_response({'stage': stage, **metadata})

@routes.get('/api-proxy/usd/stages/{stage_id}/preview')
async def get_usd_preview(request):
    stage = _stage(request); preview = pathlib.Path(stage['root_path']).parent / 'preview.usdc'
    path = preview if preview.exists() else pathlib.Path(stage['root_path'])
    return web.FileResponse(path, headers={'Content-Disposition': f'inline; filename="{path.name}"'})

@routes.patch('/api-proxy/usd/stages/{stage_id}/session')
async def patch_usd_session(request):
    stage = _stage(request); state = await request.json()
    try:
        usd_repo.save_session(stage['id'], state, 'building'); usd_service.apply_session(stage['root_path'], stage['session_path'], state)
        usd_service.export_preview(stage['root_path'], str(pathlib.Path(stage['root_path']).parent / 'preview.usdc'), stage['session_path'])
        usd_repo.save_session(stage['id'], state)
    except Exception as error:
        usd_repo.save_session(stage['id'], state, 'error', str(error)); raise web.HTTPUnprocessableEntity(reason=str(error))
    return web.json_response({'ok': True})

@routes.get('/api-proxy/usd/stages/{stage_id}/export/session')
async def export_usd_session(request):
    stage = _stage(request); path = pathlib.Path(stage['session_path'])
    if not path.exists(): path.write_text('#usda 1.0\n', encoding='utf-8')
    return web.FileResponse(path, headers={'Content-Disposition': f'attachment; filename="{path.name}"'})

@routes.get('/api-proxy/usd/stages/{stage_id}/export/usdz')
async def export_usdz(request):
    stage = _stage(request); output = pathlib.Path(stage['root_path']).parent / f"{stage['name']}.usdz"
    usd_service.package_usdz(stage['root_path'], str(output), stage.get('session_path'))
    return web.FileResponse(output, headers={'Content-Disposition': f'attachment; filename="{output.name}"'})

@routes.delete('/api-proxy/usd/stages/{stage_id}')
async def delete_usd_stage(request):
    stage = _stage(request); usd_repo.delete_stage(stage['id'], int(stage['user_id'])); shutil.rmtree(pathlib.Path(stage['root_path']).parent, ignore_errors=True)
    return web.json_response({'ok': True})
