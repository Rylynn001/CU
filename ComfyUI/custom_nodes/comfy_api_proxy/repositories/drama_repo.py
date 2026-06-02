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
                SELECT ch.* FROM characters ch
                JOIN episode_characters ec ON ec.character_id=ch.id
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
                SELECT s.* FROM scenes s
                JOIN episode_scenes es ON es.scene_id=s.id
                WHERE es.episode_id=%s AND s.deleted_at IS NULL
            """, (episode_id,))
            return _ser_list(c.fetchall())
    finally:
        conn.close()
