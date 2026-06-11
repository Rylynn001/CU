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


# 内置音色库（与前端 VOICE_PROFILES 保持一致）
VOICE_LIBRARY = [
    {"id": "longxiaochun", "name": "龙小淳", "gender": "female", "style": "活泼甜美"},
    {"id": "longxiaoxia",  "name": "龙小夏", "gender": "female", "style": "温柔知性"},
    {"id": "longxiaobai",  "name": "龙小白", "gender": "female", "style": "清冷气质"},
    {"id": "longlaotie",   "name": "龙老铁", "gender": "male",   "style": "东北豪爽"},
    {"id": "longshuo",     "name": "龙硕",   "gender": "male",   "style": "稳重成熟"},
    {"id": "longxiaoshu",  "name": "龙小树", "gender": "male",   "style": "青年阳光"},
    {"id": "longyue",      "name": "龙悦",   "gender": "female", "style": "优雅大气"},
    {"id": "longfei",      "name": "龙飞",   "gender": "male",   "style": "深沉有力"},
]


class VoiceTools:
    def __init__(self, episode_id: int, db_config: Optional[dict] = None):
        self.episode_id = episode_id
        self._db_config = db_config or _default_db_config()

    def _conn(self) -> pymysql.connections.Connection:
        return pymysql.connect(**self._db_config)

    def list_voices(self) -> dict:
        """返回可用音色列表"""
        return {"voices": VOICE_LIBRARY}

    def get_characters(self) -> dict:
        """获取当前集所有角色及其已分配的音色"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ch.id, ch.name, ch.role, ch.personality, ch.appearance, ch.voice_style
                    FROM characters ch
                    JOIN episode_characters ec ON ec.character_id = ch.id
                    WHERE ec.episode_id = %s AND ch.deleted_at IS NULL
                """, (self.episode_id,))
                rows = cur.fetchall()
        return {"characters": list(rows)}

    def assign_voice(self, character_id: int, voice_id: str) -> dict:
        """为指定角色分配音色"""
        valid_ids = {v["id"] for v in VOICE_LIBRARY}
        if voice_id not in valid_ids:
            return {"error": f"音色 {voice_id} 不存在，请从 list_voices 返回的列表中选择"}
        ts = _now()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE characters SET voice_style=%s, updated_at=%s WHERE id=%s AND deleted_at IS NULL",
                    (voice_id, ts, character_id),
                )
            conn.commit()
        voice = next(v for v in VOICE_LIBRARY if v["id"] == voice_id)
        return {"message": f"已为角色 {character_id} 分配音色 {voice['name']}", "voice_id": voice_id}
