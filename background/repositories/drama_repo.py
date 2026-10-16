"""短剧相关数据库操作"""
from typing import Optional
from database import execute_query


# ========== Drama 相关操作 ==========

def get_all_dramas() -> list[dict]:
    """获取所有短剧列表（含统计数据）"""
    return execute_query(
        '''SELECT d.*,
              (SELECT COUNT(*) FROM episodes e WHERE e.drama_id=d.id AND e.deleted_at IS NULL) AS episode_count,
              (SELECT COUNT(*) FROM characters ch WHERE ch.drama_id=d.id AND ch.deleted_at IS NULL) AS character_count,
              (SELECT COUNT(*) FROM scenes s WHERE s.drama_id=d.id AND s.deleted_at IS NULL) AS scene_count
           FROM dramas d
           WHERE d.deleted_at IS NULL
           ORDER BY d.updated_at DESC''',
        fetch_all=True
    ) or []


def create_drama(title: str, description: str | None, genre: str | None,
                 style: str, total_episodes: int) -> dict:
    """创建短剧并返回完整记录"""
    drama_id = execute_query(
        '''INSERT INTO dramas (title, description, genre, style, total_episodes, status, created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, 'draft', NOW(), NOW())''',
        (title, description, genre, style, total_episodes)
    )
    return get_drama_by_id(drama_id)


def get_drama_by_id(drama_id: int) -> Optional[dict]:
    """根据ID获取短剧基础信息"""
    return execute_query(
        'SELECT * FROM dramas WHERE id = %s AND deleted_at IS NULL',
        (drama_id,),
        fetch_one=True
    )


def get_drama_episodes(drama_id: int) -> list[dict]:
    """获取短剧的集数列表"""
    return execute_query(
        '''SELECT id, episode_number, title, status, script_content IS NOT NULL AS has_script
           FROM episodes WHERE drama_id = %s AND deleted_at IS NULL
           ORDER BY episode_number''',
        (drama_id,),
        fetch_all=True
    ) or []


def get_drama_characters(drama_id: int) -> list[dict]:
    """获取短剧的角色列表"""
    return execute_query(
        'SELECT id, name, role FROM characters WHERE drama_id = %s AND deleted_at IS NULL',
        (drama_id,),
        fetch_all=True
    ) or []


def get_drama_scenes(drama_id: int) -> list[dict]:
    """获取短剧的场景列表"""
    return execute_query(
        'SELECT id, location, time FROM scenes WHERE drama_id = %s AND deleted_at IS NULL',
        (drama_id,),
        fetch_all=True
    ) or []


def update_drama(drama_id: int, updates: dict) -> None:
    """更新短剧字段"""
    if not updates:
        return

    sets = ', '.join(f'{k} = %s' for k in updates)
    execute_query(
        f'UPDATE dramas SET {sets}, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (*updates.values(), drama_id)
    )


def delete_drama(drama_id: int) -> int:
    """软删除短剧，返回影响行数"""
    return execute_query(
        'UPDATE dramas SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (drama_id,)
    )


# ========== Episode 相关操作 ==========

def create_episode(drama_id: int, episode_number: int, title: str | None,
                   content: str | None) -> dict:
    """创建集并返回完整记录"""
    episode_id = execute_query(
        '''INSERT INTO episodes (drama_id, episode_number, title, content, status, created_at, updated_at)
           VALUES (%s, %s, %s, %s, 'draft', NOW(), NOW())''',
        (drama_id, episode_number, title, content)
    )
    return get_episode_by_id(episode_id)


def get_episode_by_id(episode_id: int) -> Optional[dict]:
    """根据ID获取集信息"""
    return execute_query(
        'SELECT * FROM episodes WHERE id = %s AND deleted_at IS NULL',
        (episode_id,),
        fetch_one=True
    )


def get_episode_by_number(drama_id: int, episode_number: int) -> Optional[dict]:
    """根据短剧ID和集数获取集信息"""
    return execute_query(
        'SELECT * FROM episodes WHERE drama_id = %s AND episode_number = %s AND deleted_at IS NULL',
        (drama_id, episode_number),
        fetch_one=True
    )


def update_episode(episode_id: int, updates: dict) -> None:
    """更新集字段"""
    if not updates:
        return

    sets = ', '.join(f'{k} = %s' for k in updates)
    execute_query(
        f'UPDATE episodes SET {sets}, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (*updates.values(), episode_id)
    )


def delete_episode(episode_id: int) -> int:
    """软删除集，返回影响行数"""
    return execute_query(
        'UPDATE episodes SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (episode_id,)
    )


def get_episode_characters(episode_id: int) -> list[dict]:
    """获取集的角色列表（包含关联资产）"""
    return execute_query(
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


def get_episode_scenes(episode_id: int) -> list[dict]:
    """获取集的场景列表（包含关联资产）"""
    return execute_query(
        '''SELECT s.*,
             a.location AS image_url
           FROM scenes s
           JOIN episode_scenes es ON es.scene_id = s.id
           LEFT JOIN assets a ON a.id = s.asset_id
           WHERE es.episode_id = %s AND s.deleted_at IS NULL''',
        (episode_id,),
        fetch_all=True
    ) or []


def update_episode_video_url(episode_id: int, video_url: str) -> None:
    """更新集的视频URL"""
    execute_query(
        'UPDATE episodes SET video_url = %s WHERE id = %s',
        (video_url, episode_id)
    )


# ========== Storyboard 相关操作 ==========

def get_episode_storyboards(episode_id: int) -> list[dict]:
    """获取集的所有分镜"""
    return execute_query(
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


def create_storyboard(episode_id: int, sequence: int, dialogue: str | None) -> dict:
    """创建分镜并返回完整记录"""
    storyboard_id = execute_query(
        '''INSERT INTO storyboards (episode_id, sequence, dialogue, created_at, updated_at)
           VALUES (%s, %s, %s, NOW(), NOW())''',
        (episode_id, sequence, dialogue),
        return_lastrowid=True
    )
    return execute_query(
        'SELECT * FROM storyboards WHERE id = %s',
        (storyboard_id,)
    )


def get_storyboard_by_id(storyboard_id: int) -> Optional[dict]:
    """根据ID获取分镜信息"""
    return execute_query(
        'SELECT * FROM storyboards WHERE id = %s AND deleted_at IS NULL',
        (storyboard_id,),
        fetch_one=True
    )


def update_storyboard(storyboard_id: int, updates: dict) -> None:
    """更新分镜字段"""
    if not updates:
        return

    sets = ', '.join(f'{k} = %s' for k in updates)
    execute_query(
        f'UPDATE storyboards SET {sets}, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (*updates.values(), storyboard_id)
    )


def delete_storyboard(storyboard_id: int) -> int:
    """软删除分镜，返回影响行数"""
    return execute_query(
        'UPDATE storyboards SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (storyboard_id,)
    )


def get_storyboard_with_assets(storyboard_id: int) -> Optional[dict]:
    """获取分镜及其关联的视频和音频信息"""
    return execute_query(
        'SELECT id, video_url, tts_audio_id FROM storyboards WHERE id = %s AND deleted_at IS NULL',
        (storyboard_id,),
        fetch_one=True
    )


def update_storyboard_composed_video(storyboard_id: int, composed_url: str) -> None:
    """更新分镜的合成视频URL"""
    execute_query(
        'UPDATE storyboards SET composed_video_url = %s WHERE id = %s',
        (composed_url, storyboard_id)
    )


def update_storyboard_tts_audio(storyboard_id: int, tts_audio_id: int) -> None:
    """更新分镜的TTS音频ID"""
    execute_query(
        'UPDATE storyboards SET tts_audio_id = %s WHERE id = %s',
        (tts_audio_id, storyboard_id)
    )


def get_episode_composed_storyboards(episode_id: int) -> list[dict]:
    """获取集内所有已合成的分镜"""
    return execute_query(
        '''SELECT id, composed_video_url FROM storyboards
           WHERE episode_id = %s AND deleted_at IS NULL AND composed_video_url IS NOT NULL
           ORDER BY id''',
        (episode_id,),
        fetch_all=True
    ) or []


# ========== Character 相关操作 ==========

def update_character(character_id: int, updates: dict) -> None:
    """更新角色字段"""
    if not updates:
        return

    sets = ', '.join(f'{k} = %s' for k in updates)
    execute_query(
        f'UPDATE characters SET {sets}, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (*updates.values(), character_id)
    )


def get_character_by_id(character_id: int) -> Optional[dict]:
    """根据ID获取角色信息"""
    return execute_query(
        'SELECT id, name, timbre_id FROM characters WHERE id = %s AND deleted_at IS NULL',
        (character_id,),
        fetch_one=True
    )


def get_character_by_name(episode_id: int, name: str) -> Optional[dict]:
    """根据集ID和角色名获取角色（包含音色）"""
    return execute_query(
        '''SELECT c.id, c.name, t.voice_id as voice_style
           FROM characters c
           LEFT JOIN timbres t ON c.timbre_id = t.id
           WHERE c.episode_id = %s AND c.name = %s AND c.deleted_at IS NULL
           LIMIT 1''',
        (episode_id, name),
        fetch_one=True
    )


def update_character_voice_sample(character_id: int, voice_sample_id: int) -> None:
    """更新角色的试听样本ID"""
    execute_query(
        'UPDATE characters SET voice_sample_id = %s WHERE id = %s',
        (voice_sample_id, character_id)
    )


# ========== Scene 相关操作 ==========

def update_scene_image(scene_id: int, asset_id: int) -> None:
    """更新场景图片"""
    execute_query(
        'UPDATE scenes SET asset_id = %s, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
        (asset_id, scene_id)
    )


# ========== Timbre 相关操作 ==========

def get_all_timbres() -> list[dict]:
    """获取所有音色列表"""
    return execute_query(
        'SELECT * FROM timbres WHERE deleted_at IS NULL ORDER BY id',
        fetch_all=True
    ) or []


def get_timbre_by_id(timbre_id: int) -> Optional[dict]:
    """根据ID获取音色配置"""
    return execute_query(
        'SELECT id, voice_id FROM timbres WHERE id = %s',
        (timbre_id,),
        fetch_one=True
    )


# ========== AI Voice 相关操作 ==========

def create_ai_voice(location: str, name: str, voice_style: str, language: str,
                    character_id: int) -> int:
    """创建AI语音记录，返回ID"""
    return execute_query(
        '''INSERT INTO ai_voices (location, name, voice_style, language, character_id, created_at)
           VALUES (%s, %s, %s, %s, %s, NOW())''',
        (location, name, voice_style, language, character_id)
    )


def get_ai_voice_by_id(voice_id: int) -> Optional[dict]:
    """根据ID获取AI语音信息"""
    return execute_query(
        'SELECT id, location FROM ai_voices WHERE id = %s',
        (voice_id,),
        fetch_one=True
    )


def get_ai_voice_location(voice_id: int) -> Optional[str]:
    """根据ID获取AI语音文件路径"""
    voice = execute_query(
        'SELECT location FROM ai_voices WHERE id = %s',
        (voice_id,),
        fetch_one=True
    )
    return voice['location'] if voice else None
