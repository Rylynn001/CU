"""短剧管理相关路由"""
import os
import uuid
import asyncio
import tempfile
import subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import execute_query
from config import settings
from api.auth import get_current_user

router = APIRouter()


class DramaCreate(BaseModel):
    title: str
    description: str | None = None
    genre: str | None = None
    style: str = 'realistic'
    total_episodes: int = 1


class EpisodeCreate(BaseModel):
    drama_id: int
    episode_number: int
    title: str | None = None
    content: str | None = None


class StoryboardCreate(BaseModel):
    sequence: int
    dialogue: str | None = None


# ========== Drama 路由 ==========

@router.get("/dramas")
async def list_dramas():
    """获取短剧列表"""
    dramas = execute_query(
        '''SELECT d.*,
              (SELECT COUNT(*) FROM episodes e WHERE e.drama_id=d.id AND e.deleted_at IS NULL) AS episode_count,
              (SELECT COUNT(*) FROM characters ch WHERE ch.drama_id=d.id AND ch.deleted_at IS NULL) AS character_count,
              (SELECT COUNT(*) FROM scenes s WHERE s.drama_id=d.id AND s.deleted_at IS NULL) AS scene_count
           FROM dramas d
           WHERE d.deleted_at IS NULL
           ORDER BY d.updated_at DESC''',
        fetch_all=True
    ) or []
    return {'items': dramas}


@router.post("/dramas")
async def create_drama(req: DramaCreate):
    """创建短剧"""
    drama_id = execute_query(
        '''INSERT INTO dramas (title, description, genre, style, total_episodes, status, created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, 'draft', NOW(), NOW())''',
        (req.title, req.description, req.genre, req.style, req.total_episodes)
    )

    drama = execute_query(
        'SELECT * FROM dramas WHERE id = %s',
        (drama_id,),
        fetch_one=True
    )
    return drama


@router.get("/dramas/{drama_id}")
async def get_drama(drama_id: int):
    """获取短剧详情"""
    drama = execute_query(
        'SELECT * FROM dramas WHERE id = %s AND deleted_at IS NULL',
        (drama_id,),
        fetch_one=True
    )

    if not drama:
        raise HTTPException(status_code=404, detail='剧集不存在')

    # 获取集数
    episodes = execute_query(
        '''SELECT id, episode_number, title, status, script_content IS NOT NULL AS has_script
           FROM episodes WHERE drama_id = %s AND deleted_at IS NULL
           ORDER BY episode_number''',
        (drama_id,),
        fetch_all=True
    ) or []

    # 获取角色
    characters = execute_query(
        'SELECT id, name, role FROM characters WHERE drama_id = %s AND deleted_at IS NULL',
        (drama_id,),
        fetch_all=True
    ) or []

    # 获取场景
    scenes = execute_query(
        'SELECT id, location, time FROM scenes WHERE drama_id = %s AND deleted_at IS NULL',
        (drama_id,),
        fetch_all=True
    ) or []

    drama['episodes'] = episodes
    drama['characters'] = characters
    drama['scenes'] = scenes

    return drama


@router.put("/dramas/{drama_id}")
async def update_drama(drama_id: int, data: dict):
    """更新短剧"""
    allowed = {'title', 'description', 'genre', 'style', 'total_episodes', 'status'}
    updates = {k: v for k, v in data.items() if k in allowed}

    if not updates:
        return {'ok': True}

    sets = ', '.join(f'{k} = %s' for k in updates)
    execute_query(
        f'UPDATE dramas SET {sets}, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (*updates.values(), drama_id)
    )

    return {'ok': True}


@router.delete("/dramas/{drama_id}")
async def delete_drama(drama_id: int):
    """删除短剧（软删除）"""
    result = execute_query(
        'UPDATE dramas SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (drama_id,)
    )

    if not result:
        raise HTTPException(status_code=404, detail='剧集不存在')

    return {'ok': True}


# ========== Episode 路由 ==========

@router.post("/episodes")
async def create_episode(req: EpisodeCreate):
    """创建集"""
    episode_id = execute_query(
        '''INSERT INTO episodes (drama_id, episode_number, title, content, status, created_at, updated_at)
           VALUES (%s, %s, %s, %s, 'draft', NOW(), NOW())''',
        (req.drama_id, req.episode_number, req.title, req.content)
    )

    episode = execute_query(
        'SELECT * FROM episodes WHERE id = %s',
        (episode_id,),
        fetch_one=True
    )
    return episode


@router.get("/episodes/{episode_id}")
async def get_episode(episode_id: int):
    """获取集详情"""
    episode = execute_query(
        'SELECT * FROM episodes WHERE id = %s AND deleted_at IS NULL',
        (episode_id,),
        fetch_one=True
    )

    if not episode:
        raise HTTPException(status_code=404, detail='集不存在')

    return episode


@router.put("/episodes/{episode_id}")
async def update_episode(episode_id: int, data: dict):
    """更新集"""
    allowed = {'title', 'content', 'status', 'video_url', 'script_content'}
    updates = {k: v for k, v in data.items() if k in allowed}

    if not updates:
        return {'ok': True}

    sets = ', '.join(f'{k} = %s' for k in updates)
    execute_query(
        f'UPDATE episodes SET {sets}, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (*updates.values(), episode_id)
    )

    return {'ok': True}


@router.delete("/episodes/{episode_id}")
async def delete_episode(episode_id: int):
    """删除集（软删除）"""
    result = execute_query(
        'UPDATE episodes SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (episode_id,)
    )

    if not result:
        raise HTTPException(status_code=404, detail='集不存在')

    return {'ok': True}


@router.get("/dramas/{drama_id}/episodes/{episode_number}")
async def get_episode_by_number(drama_id: int, episode_number: int):
    """根据集数获取集"""
    episode = execute_query(
        'SELECT * FROM episodes WHERE drama_id = %s AND episode_number = %s AND deleted_at IS NULL',
        (drama_id, episode_number),
        fetch_one=True
    )

    if not episode:
        raise HTTPException(status_code=404, detail='集不存在')

    return episode


@router.get("/episodes/{episode_id}/characters")
async def get_episode_characters(episode_id: int):
    """获取集的角色列表"""
    characters = execute_query(
        '''SELECT ch.*,
             a.location AS image_url,
             av.location AS voice_sample_url,
             t.name AS timbre_name, t.voice_id AS timbre_voice_id
           FROM characters ch
           JOIN episode_characters ec ON ec.character_id = ch.id
           LEFT JOIN assets a ON a.id = ch.asset_id
           LEFT JOIN ai_voices av ON av.id = ch.voice_sample_id
           LEFT JOIN timbres t ON t.id = ch.timbre_id
           WHERE ec.episode_id = %s AND ch.deleted_at IS NULL''',
        (episode_id,),
        fetch_all=True
    ) or []

    return {'items': characters}


@router.get("/episodes/{episode_id}/scenes")
async def get_episode_scenes(episode_id: int):
    """获取集的场景列表"""
    scenes = execute_query(
        '''SELECT s.*,
             a.location AS image_url
           FROM scenes s
           JOIN episode_scenes es ON es.scene_id = s.id
           LEFT JOIN assets a ON a.id = s.asset_id
           WHERE es.episode_id = %s AND s.deleted_at IS NULL''',
        (episode_id,),
        fetch_all=True
    ) or []

    return {'items': scenes}


# ========== Storyboard 路由 ==========

@router.get("/episodes/{episode_id}/storyboards")
async def list_storyboards(episode_id: int):
    """获取分镜列表"""
    items = execute_query(
        '''SELECT s.*,
             IFNULL(GROUP_CONCAT(sc.character_id ORDER BY sc.character_id), '') AS character_ids,
             fa.location AS first_frame_image,
             la.location AS last_frame_image,
             av.location AS tts_audio_url
           FROM storyboards s
           LEFT JOIN storyboard_characters sc ON sc.storyboard_id = s.id
           LEFT JOIN assets fa ON fa.id = s.first_asset_id
           LEFT JOIN assets la ON la.id = s.last_asset_id
           LEFT JOIN ai_voices av ON av.id = s.tts_audio_id
           WHERE s.episode_id = %s AND s.deleted_at IS NULL
           GROUP BY s.id
           ORDER BY s.storyboard_number ASC, s.id ASC''',
        (episode_id,),
        fetch_all=True
    ) or []

    return {'items': items}


@router.post("/episodes/{episode_id}/storyboards")
async def create_storyboard(episode_id: int, req: StoryboardCreate):
    """创建分镜"""
    storyboard_id = execute_query(
        '''INSERT INTO storyboards (episode_id, sequence, dialogue, created_at, updated_at)
           VALUES (%s, %s, %s, NOW(), NOW())''',
        (episode_id, req.sequence, req.dialogue),
        return_lastrowid=True
    )

    storyboard = execute_query(
        'SELECT * FROM storyboards WHERE id = %s',
        (storyboard_id,)
    )
    return storyboard


@router.put("/storyboards/{storyboard_id}")
async def update_storyboard(storyboard_id: int, data: dict):
    """更新分镜"""
    allowed = {'sequence', 'dialogue', 'video_url', 'tts_audio_id', 'composed_video_url', 'character_id', 'scene_id'}
    updates = {k: v for k, v in data.items() if k in allowed}

    if not updates:
        return {'ok': True}

    sets = ', '.join(f'{k} = %s' for k in updates)
    execute_query(
        f'UPDATE storyboards SET {sets}, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (*updates.values(), storyboard_id)
    )

    return {'ok': True}


@router.delete("/storyboards/{storyboard_id}")
async def delete_storyboard(storyboard_id: int):
    """删除分镜（软删除）"""
    result = execute_query(
        'UPDATE storyboards SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (storyboard_id,)
    )

    if not result:
        raise HTTPException(status_code=404, detail='分镜不存在')

    return {'ok': True}


# ========== 其他辅助路由 ==========

@router.get("/timbres")
async def list_timbres():
    """获取音色列表"""
    items = execute_query(
        'SELECT * FROM timbres WHERE deleted_at IS NULL ORDER BY id',
        fetch_all=True
    ) or []
    return {'items': items}


@router.put("/characters/{character_id}")
async def update_character(character_id: int, data: dict):
    """更新角色"""
    allowed = {'name', 'role', 'timbre_id', 'voice_sample_id', 'asset_id'}
    updates = {k: v for k, v in data.items() if k in allowed}

    if not updates:
        return {'ok': True}

    sets = ', '.join(f'{k} = %s' for k in updates)
    execute_query(
        f'UPDATE characters SET {sets}, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (*updates.values(), character_id)
    )

    return {'ok': True}


@router.put("/characters/{character_id}/image")
async def update_character_image(character_id: int, data: dict):
    """更新角色图片"""
    asset_id = data.get('asset_id')
    if not asset_id:
        raise HTTPException(status_code=400, detail='asset_id 为必填项')

    execute_query(
        'UPDATE characters SET asset_id = %s, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (asset_id, character_id)
    )

    return {'ok': True}


@router.put("/scenes/{scene_id}/image")
async def update_scene_image(scene_id: int, data: dict):
    """更新场景图片"""
    asset_id = data.get('asset_id')
    if not asset_id:
        raise HTTPException(status_code=400, detail='asset_id 为必填项')

    execute_query(
        'UPDATE scenes SET asset_id = %s, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (asset_id, scene_id)
    )

    return {'ok': True}


@router.post("/characters/{character_id}/generate-voice-sample")
async def generate_voice_sample(
    character_id: int,
    current_user: dict = Depends(get_current_user)
):
    """为角色生成试听样本"""
    # TODO: 实现 TTS 生成逻辑
    raise HTTPException(status_code=501, detail='功能待实现')


@router.post("/storyboards/{storyboard_id}/generate-tts")
async def generate_storyboard_tts(
    storyboard_id: int,
    language: str = 'zh',
    current_user: dict = Depends(get_current_user)
):
    """为分镜台词生成配音"""
    # TODO: 实现 TTS 生成逻辑
    raise HTTPException(status_code=501, detail='功能待实现')


@router.post("/storyboards/{storyboard_id}/compose")
async def compose_storyboard(
    storyboard_id: int,
    current_user: dict = Depends(get_current_user)
):
    """合成单个分镜：将视频和配音合并"""
    import subprocess
    import uuid
    from pathlib import Path

    # 查询分镜
    sb = execute_query(
        'SELECT id, video_url, tts_audio_id FROM storyboards WHERE id = %s AND deleted_at IS NULL',
        (storyboard_id,),
        fetch_one=True
    )
    if not sb:
        raise HTTPException(status_code=404, detail='分镜不存在')

    video_url = sb.get('video_url')
    if not video_url:
        raise HTTPException(status_code=400, detail='分镜尚无视频')

    tts_audio_id = sb.get('tts_audio_id')
    output_dir = Path(settings.OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 解析视频路径
    if video_url.startswith('/api/api-proxy/output/'):
        video_filename = video_url.split('/')[-1]
        video_path = output_dir / video_filename
    else:
        video_path = Path(video_url)

    if not video_path.exists():
        raise HTTPException(status_code=400, detail=f'视频文件不存在: {video_url}')

    # 若无配音，直接返回原视频
    if not tts_audio_id:
        execute_query(
            'UPDATE storyboards SET composed_video_url = %s WHERE id = %s',
            (video_url, storyboard_id)
        )
        return {'composed_video_url': video_url}

    # 查询配音文件
    audio = execute_query(
        'SELECT location FROM ai_voices WHERE id = %s',
        (tts_audio_id,),
        fetch_one=True
    )
    if not audio:
        execute_query(
            'UPDATE storyboards SET composed_video_url = %s WHERE id = %s',
            (video_url, storyboard_id)
        )
        return {'composed_video_url': video_url}

    audio_path = Path(audio['location'])
    if not audio_path.exists():
        execute_query(
            'UPDATE storyboards SET composed_video_url = %s WHERE id = %s',
            (video_url, storyboard_id)
        )
        return {'composed_video_url': video_url}

    # 使用 ffmpeg 混流
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

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail='ffmpeg 合成失败')

    composed_url = f'/api/api-proxy/output/{out_filename}'
    execute_query(
        'UPDATE storyboards SET composed_video_url = %s WHERE id = %s',
        (composed_url, storyboard_id)
    )

    return {'composed_video_url': composed_url}


@router.post("/episodes/{episode_id}/merge")
async def merge_episode(
    episode_id: int,
    current_user: dict = Depends(get_current_user)
):
    """将集内所有已合成镜头按顺序拼接为完整视频"""
    import subprocess
    import uuid
    import tempfile
    from pathlib import Path

    # 查询剧集
    ep = execute_query(
        'SELECT id FROM episodes WHERE id = %s AND deleted_at IS NULL',
        (episode_id,),
        fetch_one=True
    )
    if not ep:
        raise HTTPException(status_code=404, detail='集不存在')

    # 查询所有已合成的分镜
    sbs = execute_query(
        'SELECT id, composed_video_url FROM storyboards WHERE episode_id = %s AND deleted_at IS NULL AND composed_video_url IS NOT NULL ORDER BY id',
        (episode_id,),
        fetch_all=True
    ) or []

    if not sbs:
        raise HTTPException(status_code=400, detail='没有已合成的镜头')

    output_dir = Path(settings.OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 构建视频路径列表
    video_paths = []
    for sb in sbs:
        url = sb['composed_video_url']
        if url.startswith('/api/api-proxy/output/'):
            filename = url.split('/')[-1]
            p = output_dir / filename
        else:
            p = Path(url)

        if p.exists():
            video_paths.append(p)

    if not video_paths:
        raise HTTPException(status_code=400, detail='所有已合成镜头的文件均不存在')

    # 创建 concat 文件列表
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        list_path = Path(f.name)
        for p in video_paths:
            # 转义单引号
            escaped = str(p).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

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
        result = subprocess.run(cmd, capture_output=True)
    finally:
        list_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail='ffmpeg 拼接失败')

    merged_url = f'/api/api-proxy/output/{out_filename}'
    execute_query(
        'UPDATE episodes SET video_url = %s WHERE id = %s',
        (merged_url, episode_id)
    )

    return {'merged_video_url': merged_url}


@router.get("/voice/{filename}")
async def serve_voice_file(filename: str):
    """提供语音文件下载"""
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail='Invalid filename')

    voice_dir = Path(settings.VOICE_DIR)
    file_path = voice_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail='文件不存在')

    return FileResponse(file_path)


# ========== TTS 配音功能 ==========

class TTSRequest(BaseModel):
    language: str = 'zh'


class VoiceSampleRequest(BaseModel):
    language: str = 'zh'
    text: str | None = None


@router.post("/characters/{character_id}/generate-voice-sample")
async def generate_voice_sample(character_id: int, req: VoiceSampleRequest):
    """为角色生成试听样本，写入 ai_voices 并更新 characters.voice_sample_id"""
    import httpx

    # 查询角色信息
    character = execute_query(
        'SELECT id, name, timbre_id FROM characters WHERE id = %s AND deleted_at IS NULL',
        (character_id,),
        fetch_one=True
    )
    if not character:
        raise HTTPException(status_code=404, detail='角色不存在')

    timbre_id = character.get('timbre_id')
    if not timbre_id:
        raise HTTPException(status_code=400, detail='角色未分配音色')

    # 查询音色配置
    timbre = execute_query(
        'SELECT id, voice_id FROM timbres WHERE id = %s',
        (timbre_id,),
        fetch_one=True
    )
    if not timbre or not timbre.get('voice_id'):
        raise HTTPException(status_code=400, detail='音色配置无效')

    # 生成试听文本
    sample_text = req.text or f"大家好，我是{character['name']}。"

    # 调用 TTS
    voice_id = await _call_tts(
        voice_style=timbre['voice_id'],
        name=character['name'],
        text=sample_text,
        language=req.language,
        character_id=character_id
    )

    # 更新角色的 voice_sample_id
    execute_query(
        'UPDATE characters SET voice_sample_id = %s WHERE id = %s',
        (voice_id, character_id)
    )

    # 返回生成的语音
    voice = execute_query(
        'SELECT id, location FROM ai_voices WHERE id = %s',
        (voice_id,),
        fetch_one=True
    )

    return {'ok': True, 'id': voice_id, 'location': voice['location']}


@router.post("/storyboards/{storyboard_id}/generate-tts")
async def generate_storyboard_tts(storyboard_id: int, req: TTSRequest):
    """为分镜台词生成配音，写入 ai_voices 并更新 storyboards.tts_audio_id"""

    # 查询分镜信息
    sb = execute_query(
        'SELECT id, episode_id, dialogue FROM storyboards WHERE id = %s',
        (storyboard_id,),
        fetch_one=True
    )
    if not sb:
        raise HTTPException(status_code=404, detail='分镜不存在')

    dialogue = (sb.get('dialogue') or '').strip()
    if not dialogue:
        raise HTTPException(status_code=400, detail='分镜无对白内容')

    # 解析说话人，格式："角色名：台词" 或 "旁白：文案"
    if '：' in dialogue:
        speaker, text = dialogue.split('：', 1)
    elif ':' in dialogue:
        speaker, text = dialogue.split(':', 1)
    else:
        speaker, text = '', dialogue

    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail='分镜对白内容为空')

    speaker = speaker.strip()

    # 查询角色的音色配置
    char = execute_query(
        '''SELECT c.id, c.name, t.voice_id as voice_style
           FROM characters c
           LEFT JOIN timbres t ON c.timbre_id = t.id
           WHERE c.episode_id = %s AND c.name = %s AND c.deleted_at IS NULL
           LIMIT 1''',
        (sb['episode_id'], speaker),
        fetch_one=True
    )

    if not char or not char.get('voice_style'):
        raise HTTPException(status_code=400, detail=f'找不到角色"{speaker}"的音色，请先分配音色')

    # 调用 TTS
    voice_id = await _call_tts(
        voice_style=char['voice_style'],
        name=speaker,
        text=text,
        language=req.language,
        character_id=char['id']
    )

    # 更新分镜的 tts_audio_id
    execute_query(
        'UPDATE storyboards SET tts_audio_id = %s WHERE id = %s',
        (voice_id, storyboard_id)
    )

    # 返回生成的语音
    voice = execute_query(
        'SELECT id, location FROM ai_voices WHERE id = %s',
        (voice_id,),
        fetch_one=True
    )

    return {'ok': True, 'id': voice_id, 'location': voice['location']}


async def _call_tts(voice_style: str, name: str, text: str, language: str, character_id: int) -> int:
    """调用 MiniMax TTS，保存文件，写 ai_voices，返回 ai_voices.id"""
    import httpx

    if not settings.MINIMAX_API_KEY:
        raise HTTPException(status_code=500, detail='MINIMAX_API_KEY 未配置')

    payload = {
        'model': 'speech-02-turbo',
        'text': text,
        'stream': False,
        'voice_setting': {
            'voice_id': voice_style,
            'speed': 1,
            'vol': 1,
            'pitch': 1
        },
        'audio_setting': {
            'audio_sample_rate': 32000,
            'bitrate': 128000,
            'format': 'mp3',
            'channel': 2
        }
    }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {settings.MINIMAX_API_KEY}'
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f'{settings.MINIMAX_BASE_URL}/t2a_v2',
                headers=headers,
                json=payload
            )
            resp.raise_for_status()
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f'TTS 请求失败: {e}')

    # 解析响应
    content_type = resp.headers.get('Content-Type', '')
    if 'audio' in content_type:
        audio_bytes = resp.content
    else:
        data = resp.json()
        audio_hex = data.get('data', {}).get('audio')
        if not audio_hex:
            raise HTTPException(status_code=500, detail='TTS 返回无音频数据')
        audio_bytes = bytes.fromhex(audio_hex)

    # 保存文件
    voice_dir = Path(settings.VOICE_DIR)
    filename = f'{uuid.uuid4().hex}.mp3'
    file_path = voice_dir / filename
    file_path.write_bytes(audio_bytes)

    # 写入数据库
    voice_id = execute_query(
        '''INSERT INTO ai_voices (location, name, voice_style, language, character_id, created_at)
           VALUES (%s, %s, %s, %s, %s, NOW())''',
        (str(file_path), name, voice_style, language, character_id)
    )

    return voice_id
