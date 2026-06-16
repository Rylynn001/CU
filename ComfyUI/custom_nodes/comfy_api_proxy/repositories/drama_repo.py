"""drama / episode CRUD"""
import logging
from datetime import datetime, date
from .database import get_db_connection

logger = logging.getLogger('comfy_api_proxy')

_NOW = lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _ser(row):
    """把查询结果里的 datetime/date 转成字符串，让 json_response 能序列化。"""
    if row is None:
        return None
    return {k: (v.isoformat() if isinstance(v, (datetime, date)) else v) for k, v in row.items()}


def _ser_list(rows):
    return [_ser(r) for r in rows]


# ── Drama ──────────────────────────────────────────────────────────────────

def list_dramas() -> list:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT d.*,
                  (SELECT COUNT(*) FROM episodes e WHERE e.drama_id=d.id AND e.deleted_at IS NULL) AS episode_count,
                  (SELECT COUNT(*) FROM characters ch WHERE ch.drama_id=d.id AND ch.deleted_at IS NULL) AS character_count,
                  (SELECT COUNT(*) FROM scenes s WHERE s.drama_id=d.id AND s.deleted_at IS NULL) AS scene_count
                FROM dramas d
                WHERE d.deleted_at IS NULL
                ORDER BY d.updated_at DESC
            """)
            return _ser_list(c.fetchall())
    finally:
        conn.close()


def get_drama(drama_id: int) -> dict | None:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute("SELECT * FROM dramas WHERE id=%s AND deleted_at IS NULL", (drama_id,))
            drama = c.fetchone()
            if not drama:
                return None
            c.execute("""
                SELECT id, episode_number, title, status, script_content IS NOT NULL AS has_script
                FROM episodes WHERE drama_id=%s AND deleted_at IS NULL
                ORDER BY episode_number
            """, (drama_id,))
            drama['episodes'] = _ser_list(c.fetchall())
            c.execute("SELECT id, name, role FROM characters WHERE drama_id=%s AND deleted_at IS NULL", (drama_id,))
            drama['characters'] = _ser_list(c.fetchall())
            c.execute("SELECT id, location, time FROM scenes WHERE drama_id=%s AND deleted_at IS NULL", (drama_id,))
            drama['scenes'] = _ser_list(c.fetchall())
            return _ser(drama)
    finally:
        conn.close()


def create_drama(data: dict) -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            now = _NOW()
            c.execute("""
                INSERT INTO dramas (title, description, genre, style, total_episodes, status, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,'draft',%s,%s)
            """, (
                data.get('title', ''),
                data.get('description', ''),
                data.get('genre', ''),
                data.get('style', 'realistic'),
                data.get('total_episodes', 1),
                now, now,
            ))
            conn.commit()
            return c.lastrowid
    finally:
        conn.close()


def update_drama(drama_id: int, data: dict) -> bool:
    fields = {k: v for k, v in data.items() if k in ('title', 'description', 'genre', 'style', 'total_episodes', 'status')}
    if not fields:
        return False
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            sets = ', '.join(f'{k}=%s' for k in fields)
            vals = list(fields.values()) + [_NOW(), drama_id]
            c.execute(f"UPDATE dramas SET {sets}, updated_at=%s WHERE id=%s AND deleted_at IS NULL", vals)
            conn.commit()
            return c.rowcount > 0
    finally:
        conn.close()


def delete_drama(drama_id: int) -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            now = _NOW()
            c.execute("UPDATE dramas SET deleted_at=%s WHERE id=%s AND deleted_at IS NULL", (now, drama_id))
            conn.commit()
            return c.rowcount > 0
    finally:
        conn.close()


# ── Episode ────────────────────────────────────────────────────────────────

def get_episode(episode_id: int) -> dict | None:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute("SELECT * FROM episodes WHERE id=%s AND deleted_at IS NULL", (episode_id,))
            return _ser(c.fetchone())
    finally:
        conn.close()


def get_episode_by_number(drama_id: int, episode_number: int) -> dict | None:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT * FROM episodes WHERE drama_id=%s AND episode_number=%s AND deleted_at IS NULL",
                (drama_id, episode_number),
            )
            return _ser(c.fetchone())
    finally:
        conn.close()


def create_episode(data: dict) -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            now = _NOW()
            c.execute("""
                INSERT INTO episodes (drama_id, episode_number, title, content, status, created_at, updated_at)
                VALUES (%s,%s,%s,%s,'draft',%s,%s)
            """, (
                data['drama_id'],
                data['episode_number'],
                data.get('title', f"第{data['episode_number']}集"),
                data.get('content', ''),
                now, now,
            ))
            new_id = c.lastrowid  # 必须在 UPDATE 之前取，UPDATE 会把 lastrowid 清零
            c.execute("UPDATE dramas SET updated_at=%s WHERE id=%s", (now, data['drama_id']))
            conn.commit()
            return new_id
    finally:
        conn.close()


def update_episode(episode_id: int, data: dict) -> bool:
    fields = {k: v for k, v in data.items() if k in ('title', 'content', 'script_content', 'status', 'description')}
    if not fields:
        return False
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            sets = ', '.join(f'{k}=%s' for k in fields)
            vals = list(fields.values()) + [_NOW(), episode_id]
            c.execute(f"UPDATE episodes SET {sets}, updated_at=%s WHERE id=%s AND deleted_at IS NULL", vals)
            conn.commit()
            return c.rowcount > 0
    finally:
        conn.close()


def delete_episode(episode_id: int) -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute("UPDATE episodes SET deleted_at=%s WHERE id=%s AND deleted_at IS NULL", (_NOW(), episode_id))
            conn.commit()
            return c.rowcount > 0
    finally:
        conn.close()


def get_episode_characters(episode_id: int) -> list:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT ch.*,
                  a.location AS image_url
                FROM characters ch
                JOIN episode_characters ec ON ec.character_id=ch.id
                LEFT JOIN assets a ON a.id=ch.asset_id
                WHERE ec.episode_id=%s AND ch.deleted_at IS NULL
            """, (episode_id,))
            return _ser_list(c.fetchall())
    finally:
        conn.close()


def get_episode_scenes(episode_id: int) -> list:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT s.*,
                  a.location AS image_url
                FROM scenes s
                JOIN episode_scenes es ON es.scene_id=s.id
                LEFT JOIN assets a ON a.id=s.asset_id
                WHERE es.episode_id=%s AND s.deleted_at IS NULL
            """, (episode_id,))
            return _ser_list(c.fetchall())
    finally:
        conn.close()


def update_scene_asset(scene_id: int, asset_id: int) -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute(
                "UPDATE scenes SET asset_id=%s, updated_at=%s WHERE id=%s AND deleted_at IS NULL",
                (asset_id, _NOW(), scene_id),
            )
            conn.commit()
            return c.rowcount > 0
    finally:
        conn.close()


# ── Timbres ────────────────────────────────────────────────────────────────

def list_timbres() -> list:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute("SELECT id, name, gender, style, provider FROM timbres WHERE deleted_at IS NULL ORDER BY sort_order ASC, id ASC")
            return _ser_list(c.fetchall())
    finally:
        conn.close()


def update_character_asset(character_id: int, asset_id: int) -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute(
                "UPDATE characters SET asset_id=%s, updated_at=%s WHERE id=%s AND deleted_at IS NULL",
                (asset_id, _NOW(), character_id),
            )
            conn.commit()
            return c.rowcount > 0
    finally:
        conn.close()


# ── Character voice ────────────────────────────────────────────────────────

def update_character_voice(character_id: int, timbre_id: int) -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute(
                "UPDATE characters SET timbre_id=%s, updated_at=%s WHERE id=%s AND deleted_at IS NULL",
                (timbre_id, _NOW(), character_id),
            )
            conn.commit()
            return c.rowcount > 0
    finally:
        conn.close()


# ── Storyboard ─────────────────────────────────────────────────────────────

def get_episode_storyboards(episode_id: int) -> list:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT s.*,
                  IFNULL(GROUP_CONCAT(sc.character_id ORDER BY sc.character_id), '') AS character_ids,
                  fa.location AS first_frame_image,
                  la.location AS last_frame_image
                FROM storyboards s
                LEFT JOIN storyboard_characters sc ON sc.storyboard_id = s.id
                LEFT JOIN assets fa ON fa.id = s.first_asset_id
                LEFT JOIN assets la ON la.id = s.last_asset_id
                WHERE s.episode_id=%s AND s.deleted_at IS NULL
                GROUP BY s.id
                ORDER BY s.storyboard_number ASC, s.id ASC
            """, (episode_id,))
            return _ser_list(c.fetchall())
    finally:
        conn.close()


def _sync_storyboard_characters(c, storyboard_id: int, character_ids):
    """同步 storyboard_characters 关联表"""
    c.execute("DELETE FROM storyboard_characters WHERE storyboard_id=%s", (storyboard_id,))
    if not character_ids:
        return
    if isinstance(character_ids, str):
        ids = [int(x) for x in character_ids.split(',') if x.strip().isdigit()]
    elif isinstance(character_ids, list):
        ids = [int(x) for x in character_ids if str(x).strip().isdigit()]
    else:
        return
    for cid in ids:
        c.execute(
            "INSERT IGNORE INTO storyboard_characters (storyboard_id, character_id) VALUES (%s,%s)",
            (storyboard_id, cid),
        )


def create_storyboard(data: dict) -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            now = _NOW()
            c.execute("""
                INSERT INTO storyboards
                  (episode_id, storyboard_number, title, shot_type, angle, movement,
                   location, time, duration, description, action, result,
                   atmosphere, dialogue, image_prompt, video_prompt,
                   bgm_prompt, sound_effect, scene_id,
                   created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                data.get('episode_id'),
                data.get('storyboard_number', data.get('sort_order', 0)),
                data.get('title', ''),
                data.get('shot_type', ''),
                data.get('angle', ''),
                data.get('movement', ''),
                data.get('location', ''),
                data.get('time', ''),
                data.get('duration', 10),
                data.get('description', ''),
                data.get('action', ''),
                data.get('result', ''),
                data.get('atmosphere', ''),
                data.get('dialogue', ''),
                data.get('image_prompt', ''),
                data.get('video_prompt', ''),
                data.get('bgm_prompt', ''),
                data.get('sound_effect', ''),
                data.get('scene_id'),
                now, now,
            ))
            new_id = c.lastrowid
            if data.get('character_ids') is not None:
                _sync_storyboard_characters(c, new_id, data['character_ids'])
            conn.commit()
            return new_id
    finally:
        conn.close()


_SB_FIELDS = {
    'storyboard_number', 'title', 'shot_type', 'angle', 'movement', 'location', 'time',
    'duration', 'description', 'action', 'result', 'atmosphere',
    'dialogue', 'image_prompt', 'video_prompt', 'bgm_prompt',
    'sound_effect', 'scene_id',
    'first_asset_id', 'last_asset_id',
}


def update_storyboard(storyboard_id: int, data: dict) -> bool:
    fields = {k: v for k, v in data.items() if k in _SB_FIELDS}
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            if fields:
                sets = ', '.join(f'{k}=%s' for k in fields)
                vals = list(fields.values()) + [_NOW(), storyboard_id]
                c.execute(
                    f"UPDATE storyboards SET {sets}, updated_at=%s WHERE id=%s AND deleted_at IS NULL",
                    vals,
                )
            if data.get('character_ids') is not None:
                _sync_storyboard_characters(c, storyboard_id, data['character_ids'])
            conn.commit()
            return True
    finally:
        conn.close()


def delete_storyboard(storyboard_id: int) -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            c.execute(
                "UPDATE storyboards SET deleted_at=%s WHERE id=%s AND deleted_at IS NULL",
                (_NOW(), storyboard_id),
            )
            conn.commit()
            return c.rowcount > 0
    finally:
        conn.close()

