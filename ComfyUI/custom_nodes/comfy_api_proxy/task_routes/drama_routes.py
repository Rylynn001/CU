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
POST   /api-proxy/characters/:id/dubbing
"""
import logging
import uuid
import requests
from aiohttp import web
from server import PromptServer
from ..repositories import drama_repo
from .. import config as cfg

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


@routes.put('/api-proxy/characters/{character_id}')
async def update_character(request: web.Request):
    character_id = int(request.match_info['character_id'])
    body = await request.json()
    try:
        drama_repo.update_character(character_id, body)
        return web.json_response({'ok': True})
    except Exception as e:
        logger.error(f'[character] update error: {e}')
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


@routes.post('/api-proxy/characters/{character_id}/generate-voice-sample')
async def generate_voice_sample(request: web.Request):
    """为角色生成试听样本，写入 ai_voices 并更新 characters.voice_sample_id"""
    character_id = int(request.match_info['character_id'])
    try:
        body = await request.json()
    except Exception:
        body = {}
    language = body.get('language', 'zh')

    character = drama_repo.get_character(character_id)
    if not character:
        raise web.HTTPNotFound(reason='角色不存在')

    timbre_id = character.get('timbre_id')
    if not timbre_id:
        raise web.HTTPBadRequest(reason='角色未分配音色')

    timbre = drama_repo.get_timbre(timbre_id)
    if not timbre or not timbre.get('voice_id'):
        raise web.HTTPBadRequest(reason='音色配置无效')

    sample_text = body.get('text') or f"大家好，我是{character['name']}。"
    voice_id = await _call_tts(timbre['voice_id'], character['name'], sample_text, language, character_id)
    drama_repo.update_character_voice_sample(character_id, voice_id)

    voice = drama_repo.get_ai_voice(voice_id)
    logger.info(f'[voice-sample] 角色 {character_id} 试听生成: ai_voice_id={voice_id}')
    return web.json_response({'ok': True, 'id': voice_id, 'location': voice['location']})


@routes.post('/api-proxy/storyboards/{storyboard_id}/generate-tts')
async def generate_storyboard_tts(request: web.Request):
    """为分镜台词生成配音，写入 ai_voices 并更新 storyboards.tts_audio_id"""
    storyboard_id = int(request.match_info['storyboard_id'])
    body = await request.json()
    language = body.get('language', 'zh')

    sb = drama_repo.get_storyboard(storyboard_id)
    if not sb:
        raise web.HTTPNotFound(reason='分镜不存在')

    dialogue = (sb.get('dialogue') or '').strip()
    if not dialogue:
        raise web.HTTPBadRequest(reason='分镜无对白内容')

    # 解析说话人，格式："角色名：台词" 或 "旁白：文案"
    if '：' in dialogue:
        speaker, text = dialogue.split('：', 1)
    elif ':' in dialogue:
        speaker, text = dialogue.split(':', 1)
    else:
        speaker, text = '', dialogue
    text = text.strip()
    if not text:
        raise web.HTTPBadRequest(reason='分镜对白内容为空')

    char = drama_repo.get_voice_style_by_speaker(sb['episode_id'], speaker.strip())
    if not char or not char.get('voice_style'):
        raise web.HTTPBadRequest(reason=f'找不到角色"{speaker.strip()}"的音色，请先分配音色')

    voice_id = await _call_tts(char['voice_style'], speaker.strip(), text, language, char['id'])
    drama_repo.update_storyboard_tts(storyboard_id, voice_id)

    voice = drama_repo.get_ai_voice(voice_id)
    logger.info(f'[storyboard-tts] 分镜 {storyboard_id} 配音生成: ai_voice_id={voice_id}')
    return web.json_response({'ok': True, 'id': voice_id, 'location': voice['location']})


async def _call_tts(voice_style: str, name: str, text: str, language: str, character_id: int) -> int:
    """调 MiniMax TTS，保存文件，写 ai_voices，返回 ai_voices.id"""
    minimax_cfg = cfg.get_minimax_config()
    if not minimax_cfg['api_key']:
        raise web.HTTPInternalServerError(reason='MINIMAX_API_KEY 未配置')

    payload = {
        'model': 'speech-02-turbo',
        'text': text,
        'stream': False,
        'voice_setting': {'voice_id': voice_style, 'speed': 1, 'vol': 1, 'pitch': 1},
        'audio_setting': {'audio_sample_rate': 32000, 'bitrate': 128000, 'format': 'mp3', 'channel': 2},
    }

    try:
        session = requests.Session()
        session.trust_env = False
        resp = session.post(
            f"{minimax_cfg['base_url']}/t2a_v2",
            headers={'Content-Type': 'application/json', 'Authorization': f"Bearer {minimax_cfg['api_key']}"},
            json=payload,
            timeout=60,
        )
        if not resp.ok:
            logger.error(f'[tts] MiniMax 400 响应体: {resp.text}')
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f'[tts] MiniMax 请求失败: {e}')
        raise web.HTTPInternalServerError(reason=f'TTS 请求失败: {e}')

    content_type = resp.headers.get('Content-Type', '')
    if 'audio' in content_type:
        audio_bytes = resp.content
    else:
        data = resp.json()
        audio_hex = data.get('data', {}).get('audio')
        if not audio_hex:
            logger.error(f'[tts] 未获取到音频: {data}')
            raise web.HTTPInternalServerError(reason='TTS 返回无音频数据')
        audio_bytes = bytes.fromhex(audio_hex)

    voice_dir = cfg.get_voice_dir()
    filename = f'{uuid.uuid4().hex}.mp3'
    file_path = voice_dir / filename
    file_path.write_bytes(audio_bytes)

    return drama_repo.create_ai_voice(str(file_path), name, voice_style, language, character_id)


@routes.get('/api-proxy/voice/{filename}')
async def serve_voice_file(request: web.Request):
    filename = request.match_info['filename']
    if '..' in filename or '/' in filename or '\\' in filename:
        raise web.HTTPBadRequest(reason='Invalid filename')
    file_path = cfg.get_voice_dir() / filename
    if not file_path.exists():
        raise web.HTTPNotFound()
    return web.FileResponse(file_path)


@routes.post('/api-proxy/storyboards/{storyboard_id}/compose')
async def compose_storyboard(request: web.Request):
    """合成单个分镜：将视频和配音合并，写入 composed_video_url"""
    import asyncio
    import uuid
    import pathlib

    storyboard_id = int(request.match_info['storyboard_id'])
    sb = drama_repo.get_storyboard(storyboard_id)
    if not sb:
        raise web.HTTPNotFound(reason='分镜不存在')

    video_url = sb.get('video_url')
    if not video_url:
        raise web.HTTPBadRequest(reason='分镜尚无视频')

    tts_audio_id = sb.get('tts_audio_id')

    output_dir = cfg.get_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 解析视频本地路径
    video_path = _resolve_output_url(video_url, output_dir)
    if not video_path or not video_path.exists():
        raise web.HTTPBadRequest(reason=f'视频文件不存在: {video_url}')

    # 若无配音，直接把 video_url 写入 composed_video_url
    if not tts_audio_id:
        drama_repo.update_storyboard(storyboard_id, {'composed_video_url': video_url})
        return web.json_response({'composed_video_url': video_url})

    # 有配音 → 用 ffmpeg 混流
    audio_info = drama_repo.get_ai_voice(tts_audio_id)
    if not audio_info:
        drama_repo.update_storyboard(storyboard_id, {'composed_video_url': video_url})
        return web.json_response({'composed_video_url': video_url})

    audio_path = pathlib.Path(audio_info['location'])
    if not audio_path.exists():
        drama_repo.update_storyboard(storyboard_id, {'composed_video_url': video_url})
        return web.json_response({'composed_video_url': video_url})

    out_filename = f'{uuid.uuid4().hex}.mp4'
    out_path = output_dir / out_filename

    cmd = [
        'ffmpeg', '-y',
        '-i', str(video_path),
        '-i', str(audio_path),
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-shortest',
        str(out_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f'[compose] ffmpeg 失败: {stderr.decode(errors="replace")}')
        raise web.HTTPInternalServerError(reason='ffmpeg 合成失败')

    composed_url = f'/api/api-proxy/output/{out_filename}'
    drama_repo.update_storyboard(storyboard_id, {'composed_video_url': composed_url})
    return web.json_response({'composed_video_url': composed_url})


@routes.post('/api-proxy/episodes/{episode_id}/merge')
async def merge_episode(request: web.Request):
    """将集内所有已合成镜头按顺序拼接为完整视频，写入 episodes.video_url"""
    import asyncio
    import uuid
    import pathlib
    import tempfile

    episode_id = int(request.match_info['episode_id'])
    ep = drama_repo.get_episode(episode_id)
    if not ep:
        raise web.HTTPNotFound(reason='集不存在')

    sbs = drama_repo.get_episode_storyboards(episode_id)
    composed = [s for s in sbs if s.get('composed_video_url')]
    if not composed:
        raise web.HTTPBadRequest(reason='没有已合成的镜头')

    output_dir = cfg.get_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 构建 ffmpeg concat 文件列表
    video_paths = []
    for sb in composed:
        p = _resolve_output_url(sb['composed_video_url'], output_dir)
        if p and p.exists():
            video_paths.append(p)

    if not video_paths:
        raise web.HTTPBadRequest(reason='所有已合成镜头的文件均不存在')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        list_path = pathlib.Path(f.name)
        for p in video_paths:
            f.write(f"file '{str(p).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")

    out_filename = f'{uuid.uuid4().hex}.mp4'
    out_path = output_dir / out_filename

    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', str(list_path),
        '-c', 'copy',
        str(out_path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
    finally:
        list_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        logger.error(f'[merge] ffmpeg 失败: {stderr.decode(errors="replace")}')
        raise web.HTTPInternalServerError(reason='ffmpeg 拼接失败')

    merged_url = f'/api/api-proxy/output/{out_filename}'
    drama_repo.update_episode(episode_id, {'video_url': merged_url})
    return web.json_response({'merged_video_url': merged_url})


def _resolve_output_url(url: str, output_dir) -> 'pathlib.Path | None':
    """把 /api/api-proxy/output/<filename> 或本地路径解析为绝对 Path"""
    import pathlib
    if not url:
        return None
    # 本地路径
    p = pathlib.Path(url)
    if p.exists():
        return p
    # /api/api-proxy/output/<filename>
    prefix = '/api/api-proxy/output/'
    if url.startswith(prefix):
        return output_dir / url[len(prefix):]
    # /api/view?filename=xxx&type=output
    if 'filename=' in url:
        import urllib.parse
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        fn = qs.get('filename', [None])[0]
        if fn:
            return output_dir / fn
    return None
