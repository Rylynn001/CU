"""
剧本改写工具 — 读取 episode 原始内容，改写后保存到 script_content
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


class RewriteTools:
    def __init__(self, episode_id: int, db_config: Optional[dict] = None):
        self.episode_id = episode_id
        self._db_config = db_config or _default_db_config()

    def _conn(self) -> pymysql.connections.Connection:
        return pymysql.connect(**self._db_config)

    def read_episode_script(self) -> dict:
        """读取当前集的原始内容（content）或已有剧本（script_content）"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT content, script_content FROM episodes WHERE id=%s AND deleted_at IS NULL",
                    (self.episode_id,),
                )
                row = cur.fetchone()
        if not row:
            return {"error": f"Episode not found (id={self.episode_id})"}
        content = row["script_content"] or row["content"]
        if not content:
            return {"error": f"Episode has no content (id={self.episode_id})"}
        return {"content": content, "word_count": len(content), "episode_id": self.episode_id}

    def save_script(self, content: str) -> dict:
        """将改写后的剧本保存到 script_content 字段"""
        ts = _now()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE episodes SET script_content=%s, updated_at=%s WHERE id=%s",
                    (content, ts, self.episode_id),
                )
            conn.commit()
        return {"message": "剧本保存成功", "word_count": len(content)}
