"""
音色分配工具 — 读取角色列表、音色库，为角色分配音色
"""
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


class VoiceTools:
    def __init__(self, episode_id: int, db_config: Optional[dict] = None):
        self.episode_id = episode_id
        self._db_config = db_config or _default_db_config()

    def _conn(self) -> pymysql.connections.Connection:
        return pymysql.connect(**self._db_config)

    def list_voices(self) -> dict:
        """返回数据库中可用音色列表"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, gender, style, provider FROM timbres"
                    " WHERE deleted_at IS NULL ORDER BY sort_order ASC, id ASC"
                )
                rows = cur.fetchall()
        return {"voices": list(rows)}

    def get_characters(self) -> dict:
        """获取当前集所有角色及其已分配的音色"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ch.id, ch.name, ch.role, ch.personality, ch.appearance,
                           ch.timbre_id, t.name AS timbre_name
                    FROM characters ch
                    LEFT JOIN timbres t ON t.id = ch.timbre_id
                    JOIN episode_characters ec ON ec.character_id = ch.id
                    WHERE ec.episode_id = %s AND ch.deleted_at IS NULL
                """, (self.episode_id,))
                rows = cur.fetchall()
        return {"characters": list(rows)}

    def assign_voice(self, character_id: int, timbre_id: int) -> dict:
        """为指定角色分配音色。timbre_id 为 timbres 表的主键 ID。"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name FROM timbres WHERE id=%s AND deleted_at IS NULL",
                    (timbre_id,),
                )
                timbre = cur.fetchone()
                if not timbre:
                    return {"error": f"音色 ID {timbre_id} 不存在，请从 list_voices 返回的列表中选择"}
                cur.execute(
                    "UPDATE characters SET timbre_id=%s, updated_at=%s WHERE id=%s AND deleted_at IS NULL",
                    (timbre_id, _now(), character_id),
                )
            conn.commit()
        return {"message": f"已为角色 {character_id} 分配音色 {timbre['name']}", "timbre_id": timbre_id}
