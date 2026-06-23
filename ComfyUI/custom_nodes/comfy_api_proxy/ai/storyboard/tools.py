"""
分镜拆解工具 — 读取剧本/角色/场景上下文，保存分镜数据
"""
import json
import pymysql
import pymysql.cursors
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _default_db_config() -> dict:
    from ...config import get_db_config
    cfg = get_db_config()
    cfg['port'] = int(cfg.get('port', 3306))
    cfg['db'] = cfg.pop('database', cfg.get('db', ''))
    cfg['cursorclass'] = pymysql.cursors.DictCursor
    return cfg


class StoryboardTools:
    def __init__(self, episode_id: int, db_config: Optional[dict] = None):
        self.episode_id = episode_id
        self._db_config = db_config or _default_db_config()

    def _conn(self) -> pymysql.connections.Connection:
        return pymysql.connect(**self._db_config)

    def read_storyboard_context(self) -> dict:
        """读取剧本内容、角色列表、场景列表、已有分镜摘要"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                # 剧本内容
                cur.execute(
                    "SELECT script_content, content FROM episodes WHERE id=%s AND deleted_at IS NULL",
                    (self.episode_id,),
                )
                ep = cur.fetchone()
                if not ep:
                    return {"error": f"Episode not found (id={self.episode_id})"}
                script = ep["script_content"] or ep["content"] or ""

                # 角色列表
                cur.execute("""
                    SELECT ch.id, ch.name, ch.role, ch.personality, ch.appearance,
                           t.name AS voice_name
                    FROM characters ch
                    JOIN episode_characters ec ON ec.character_id = ch.id
                    LEFT JOIN timbres t ON t.id = ch.timbre_id
                    WHERE ec.episode_id = %s AND ch.deleted_at IS NULL
                """, (self.episode_id,))
                characters = list(cur.fetchall())

                # 场景列表
                cur.execute("""
                    SELECT s.id, s.location, s.time, s.prompt
                    FROM scenes s
                    JOIN episode_scenes es ON es.scene_id = s.id
                    WHERE es.episode_id = %s AND s.deleted_at IS NULL
                """, (self.episode_id,))
                scenes = list(cur.fetchall())

                # 已有分镜摘要（只取标题和时长，避免太长）
                cur.execute("""
                    SELECT id, storyboard_number, title, duration
                    FROM storyboards
                    WHERE episode_id = %s AND deleted_at IS NULL
                    ORDER BY storyboard_number ASC, id ASC
                """, (self.episode_id,))
                existing = list(cur.fetchall())

        return {
            "script": script,
            "script_length": len(script),
            "characters": characters,
            "scenes": scenes,
            "existing_storyboards": existing,
            "episode_id": self.episode_id,
        }

    def _sync_characters(self, cur, storyboard_id: int, character_ids):
        """同步 storyboard_characters 关联表"""
        cur.execute("DELETE FROM storyboard_characters WHERE storyboard_id=%s", (storyboard_id,))
        if not character_ids:
            return
        if isinstance(character_ids, str):
            ids = [int(x) for x in character_ids.split(',') if x.strip().isdigit()]
        elif isinstance(character_ids, list):
            ids = [int(x) for x in character_ids if str(x).strip().isdigit()]
        else:
            return
        for cid in ids:
            cur.execute(
                "INSERT IGNORE INTO storyboard_characters (storyboard_id, character_id) VALUES (%s,%s)",
                (storyboard_id, cid),
            )

    def save_storyboards(self, storyboards: list) -> dict:
        """一次性保存多个分镜（先清空当前集已有分镜，再批量插入）"""
        ts = _now()
        with self._conn() as conn:
            with conn.cursor() as cur:
                # 软删除旧分镜
                cur.execute(
                    "UPDATE storyboards SET deleted_at=%s WHERE episode_id=%s AND deleted_at IS NULL",
                    (ts, self.episode_id),
                )
                # 批量插入
                for i, sb in enumerate(storyboards):
                    cur.execute("""
                        INSERT INTO storyboards
                          (episode_id, storyboard_number, title, shot_type, angle, movement,
                           location, time, duration, description, action, result,
                           atmosphere, dialogue, image_prompt, video_prompt,
                           bgm_prompt, sound_effect, scene_id,
                           created_at, updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        self.episode_id,
                        sb.get('storyboard_number', i + 1),
                        sb.get('title', ''),
                        sb.get('shot_type', ''),
                        sb.get('angle', ''),
                        sb.get('movement', ''),
                        sb.get('location', ''),
                        sb.get('time', ''),
                        sb.get('duration', 10),
                        sb.get('description', ''),
                        sb.get('action', ''),
                        sb.get('result', ''),
                        sb.get('atmosphere', ''),
                        sb.get('dialogue', ''),
                        sb.get('image_prompt', ''),
                        sb.get('video_prompt', ''),
                        sb.get('bgm_prompt', ''),
                        sb.get('sound_effect', ''),
                        sb.get('scene_id'),
                        ts, ts,
                    ))
                    new_id = cur.lastrowid
                    if sb.get('character_ids') is not None:
                        self._sync_characters(cur, new_id, sb['character_ids'])
            conn.commit()
        return {"message": f"已保存 {len(storyboards)} 个分镜", "count": len(storyboards)}

    def update_storyboard(self, storyboard_id: int, data: dict) -> dict:
        """更新单个分镜的字段"""
        allowed = {
            'storyboard_number', 'title', 'shot_type', 'angle', 'movement', 'location', 'time',
            'duration', 'description', 'action', 'result', 'atmosphere',
            'dialogue', 'image_prompt', 'video_prompt', 'bgm_prompt',
            'sound_effect', 'scene_id',
        }
        fields = {k: v for k, v in data.items() if k in allowed}
        ts = _now()
        with self._conn() as conn:
            with conn.cursor() as cur:
                if fields:
                    sets = ', '.join(f'{k}=%s' for k in fields)
                    vals = list(fields.values()) + [ts, storyboard_id]
                    cur.execute(
                        f"UPDATE storyboards SET {sets}, updated_at=%s WHERE id=%s AND deleted_at IS NULL",
                        vals,
                    )
                if data.get('character_ids') is not None:
                    self._sync_characters(cur, storyboard_id, data['character_ids'])
            conn.commit()
        return {"message": f"分镜 {storyboard_id} 更新成功"}
