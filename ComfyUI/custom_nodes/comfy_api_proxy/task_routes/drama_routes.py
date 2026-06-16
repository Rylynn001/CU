"""
Drama / Episode CRUD 路由
GET    /api-proxy/dramas
POST   /api-proxy/dramas
GET    /api-proxy/dramas/:id
PUT    /api-proxy/dramas/:id
DELETE /api-proxy/dramas/:id
POST   /api-proxy/episodes
GET    /api-proxy/episodes/:id
PUT    /api-proxy/episodes/:id
DELETE /api-proxy/episodes/:id
GET    /api-proxy/episodes/:id/characters
GET    /api-proxy/episodes/:id/scenes
GET    /api-proxy/dramas/:drama_id/episodes/:episode_number
"""
import logging
from aiohttp import web
from server import PromptServer
from ..repositories import drama_repo

logger = logging.getLogger('comfy_api_proxy')
routes = PromptServer.instance.routes


@routes.get('/api-proxy/dramas')
async def list_dramas(request: web.Request):
    try:
        items = drama_repo.list_dramas()
        return web.json_response({'items': items})
    except Exception as e:
        logger.error(f'[drama] list error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.post('/api-proxy/dramas')
async def create_drama(request: web.Request):
    body = await request.json()
    if not body.get('title'):
        raise web.HTTPBadRequest(reason='title 为必填项')
    try:
        new_id = drama_repo.create_drama(body)
        drama = drama_repo.get_drama(new_id)
        return web.json_response(drama, status=201)
    except Exception as e:
        logger.error(f'[drama] create error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/dramas/{drama_id}')
async def get_drama(request: web.Request):
    drama_id = int(request.match_info['drama_id'])
    drama = drama_repo.get_drama(drama_id)
    if not drama:
        raise web.HTTPNotFound(reason='剧集不存在')
    return web.json_response(drama)


@routes.put('/api-proxy/dramas/{drama_id}')
async def update_drama(request: web.Request):
    drama_id = int(request.match_info['drama_id'])
    body = await request.json()
    try:
        drama_repo.update_drama(drama_id, body)
        return web.json_response({'ok': True})
    except Exception as e:
        logger.error(f'[drama] update error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.delete('/api-proxy/dramas/{drama_id}')
async def delete_drama(request: web.Request):
    drama_id = int(request.match_info['drama_id'])
    ok = drama_repo.delete_drama(drama_id)
    if not ok:
        raise web.HTTPNotFound(reason='剧集不存在')
    return web.json_response({'ok': True})


@routes.post('/api-proxy/episodes')
async def create_episode(request: web.Request):
    body = await request.json()
    if not body.get('drama_id') or not body.get('episode_number'):
        raise web.HTTPBadRequest(reason='drama_id 和 episode_number 为必填项')
    try:
        new_id = drama_repo.create_episode(body)
        ep = drama_repo.get_episode(new_id)
        return web.json_response(ep, status=201)
    except Exception as e:
        logger.error(f'[episode] create error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/episodes/{episode_id}')
async def get_episode(request: web.Request):
    episode_id = int(request.match_info['episode_id'])
    ep = drama_repo.get_episode(episode_id)
    if not ep:
        raise web.HTTPNotFound(reason='集不存在')
    return web.json_response(ep)


@routes.put('/api-proxy/episodes/{episode_id}')
async def update_episode(request: web.Request):
    episode_id = int(request.match_info['episode_id'])
    body = await request.json()
    try:
        drama_repo.update_episode(episode_id, body)
        return web.json_response({'ok': True})
    except Exception as e:
        logger.error(f'[episode] update error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.delete('/api-proxy/episodes/{episode_id}')
async def delete_episode(request: web.Request):
    episode_id = int(request.match_info['episode_id'])
    ok = drama_repo.delete_episode(episode_id)
    if not ok:
        raise web.HTTPNotFound(reason='集不存在')
    return web.json_response({'ok': True})


@routes.get('/api-proxy/timbres')
async def list_timbres(request: web.Request):
    try:
        items = drama_repo.list_timbres()
        return web.json_response({'items': items})
    except Exception as e:
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/episodes/{episode_id}/characters')
async def episode_characters(request: web.Request):
    episode_id = int(request.match_info['episode_id'])
    try:
        items = drama_repo.get_episode_characters(episode_id)
        return web.json_response({'items': items})
    except Exception as e:
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/episodes/{episode_id}/scenes')
async def episode_scenes(request: web.Request):
    episode_id = int(request.match_info['episode_id'])
    try:
        items = drama_repo.get_episode_scenes(episode_id)
        return web.json_response({'items': items})
    except Exception as e:
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/dramas/{drama_id}/episodes/{episode_number}')
async def get_episode_by_number(request: web.Request):
    drama_id = int(request.match_info['drama_id'])
    episode_number = int(request.match_info['episode_number'])
    ep = drama_repo.get_episode_by_number(drama_id, episode_number)
    if not ep:
        raise web.HTTPNotFound(reason='集不存在')
    return web.json_response(ep)


@routes.put('/api-proxy/scenes/{scene_id}/image')
async def update_scene_image(request: web.Request):
    scene_id = int(request.match_info['scene_id'])
    body = await request.json()
    asset_id = body.get('asset_id')
    if not asset_id:
        raise web.HTTPBadRequest(reason='asset_id 为必填项')
    try:
        drama_repo.update_scene_asset(scene_id, int(asset_id))
        return web.json_response({'ok': True})
    except Exception as e:
        logger.error(f'[scene] image update error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.put('/api-proxy/characters/{character_id}/image')
async def update_character_image(request: web.Request):
    character_id = int(request.match_info['character_id'])
    body = await request.json()
    asset_id = body.get('asset_id')
    if not asset_id:
        raise web.HTTPBadRequest(reason='asset_id 为必填项')
    try:
        drama_repo.update_character_asset(character_id, int(asset_id))
        return web.json_response({'ok': True})
    except Exception as e:
        logger.error(f'[character] image update error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.put('/api-proxy/characters/{character_id}/voice')
async def update_character_voice(request: web.Request):
    character_id = int(request.match_info['character_id'])
    body = await request.json()
    timbre_id = body.get('timbre_id')
    if not timbre_id:
        raise web.HTTPBadRequest(reason='timbre_id 为必填项')
    try:
        drama_repo.update_character_voice(character_id, int(timbre_id))
        return web.json_response({'ok': True})
    except Exception as e:
        logger.error(f'[character] voice update error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.get('/api-proxy/episodes/{episode_id}/storyboards')
async def list_storyboards(request: web.Request):
    episode_id = int(request.match_info['episode_id'])
    try:
        items = drama_repo.get_episode_storyboards(episode_id)
        return web.json_response({'items': items})
    except Exception as e:
        logger.error(f'[storyboard] list error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.post('/api-proxy/episodes/{episode_id}/storyboards')
async def create_storyboard(request: web.Request):
    episode_id = int(request.match_info['episode_id'])
    body = await request.json()
    body['episode_id'] = episode_id
    try:
        new_id = drama_repo.create_storyboard(body)
        items = drama_repo.get_episode_storyboards(episode_id)
        sb = next((s for s in items if s['id'] == new_id), None)
        return web.json_response(sb or {'id': new_id}, status=201)
    except Exception as e:
        logger.error(f'[storyboard] create error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.put('/api-proxy/storyboards/{storyboard_id}')
async def update_storyboard(request: web.Request):
    storyboard_id = int(request.match_info['storyboard_id'])
    body = await request.json()
    try:
        drama_repo.update_storyboard(storyboard_id, body)
        return web.json_response({'ok': True})
    except Exception as e:
        logger.error(f'[storyboard] update error: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.delete('/api-proxy/storyboards/{storyboard_id}')
async def delete_storyboard(request: web.Request):
    storyboard_id = int(request.match_info['storyboard_id'])
    ok = drama_repo.delete_storyboard(storyboard_id)
    if not ok:
        raise web.HTTPNotFound(reason='分镜不存在')
    return web.json_response({'ok': True})
