"""
角色与场景提取工具 — 对应 huobao-drama-master TS 版的 Python 移植
使用 PyMySQL 连接 MySQL，逻辑与原 TS 实现一致
"""
import pymysql
import pymysql.cursors
from datetime import datetime, timezone, date
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _ser(row: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, (datetime, date)) else v) for k, v in row.items()}


# MySQL 连接配置，可由外部覆盖
DEFAULT_DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "db": "comfyui",
    "user": "root",
    "password": "123456",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


class ExtractTools:
    def __init__(self, episode_id: int, drama_id: int, db_config: Optional[dict] = None):
        self.episode_id = episode_id
        self.drama_id = drama_id
        self._db_config = db_config or DEFAULT_DB_CONFIG

    def _conn(self) -> pymysql.connections.Connection:
        return pymysql.connect(**self._db_config)

    # ── 关联辅助 ─────────────────────────────────────────────

    def _link_char_to_episode(self, cur, character_id: int):
        cur.execute(
            "SELECT id FROM episode_characters WHERE episode_id=%s AND character_id=%s",
            (self.episode_id, character_id),
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO episode_characters (episode_id, character_id, created_at) VALUES (%s,%s,%s)",
                (self.episode_id, character_id, _now()),
            )

    def _link_scene_to_episode(self, cur, scene_id: int):
        cur.execute(
            "SELECT id FROM episode_scenes WHERE episode_id=%s AND scene_id=%s",
            (self.episode_id, scene_id),
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO episode_scenes (episode_id, scene_id, created_at) VALUES (%s,%s,%s)",
                (self.episode_id, scene_id, _now()),
            )

    # ── 1. 读取剧本 ───────────────────────────────────────────

    def read_script_for_extraction(self) -> dict:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT script_content, content FROM episodes WHERE id=%s AND deleted_at IS NULL",
                    (self.episode_id,),
                )
                row = cur.fetchone()
        if not row:
            return {"error": "Episode not found"}
        script = row["script_content"] or row["content"]
        if not script:
            return {"error": "Episode has no script content"}
        return {"script": script}

    # ── 2. 读取已有角色 ───────────────────────────────────────

    def read_existing_characters(self) -> dict:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ch.* FROM characters ch
                    JOIN episode_characters ec ON ec.character_id = ch.id
                    WHERE ec.episode_id = %s AND ch.deleted_at IS NULL
                """, (self.episode_id,))
                chars = cur.fetchall()
        return {
            "count": len(chars),
            "characters": [_ser(c) for c in chars],
        }

    # ── 3. 读取已有场景 ───────────────────────────────────────

    def read_existing_scenes(self) -> dict:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT s.* FROM scenes s
                    JOIN episode_scenes es ON es.scene_id = s.id
                    WHERE es.episode_id = %s AND s.deleted_at IS NULL
                """, (self.episode_id,))
                scenes = cur.fetchall()
        return {
            "count": len(scenes),
            "scenes": [_ser(s) for s in scenes],
        }

    # ── 4. 保存角色（去重） ───────────────────────────────────

    def save_dedup_characters(self, characters: list[dict]) -> dict:
        ts = _now()
        created = merged = 0

        with self._conn() as conn:
            with conn.cursor() as cur:
                # 先拉出该剧集所有未删除角色，按名字建索引
                cur.execute(
                    "SELECT * FROM characters WHERE drama_id=%s AND deleted_at IS NULL",
                    (self.drama_id,),
                )
                existing_map = {r["name"]: r for r in cur.fetchall()}

                for char in characters:
                    name = char["name"]
                    if name in existing_map:
                        old = existing_map[name]
                        # 已存在：有新值才覆盖，保留原有非空内容
                        cur.execute(
                            """UPDATE characters SET
                                role        = IF(%s != '' AND %s IS NOT NULL, %s, role),
                                description = IF(%s != '' AND %s IS NOT NULL, %s, description),
                                appearance  = IF(%s != '' AND %s IS NOT NULL, %s, appearance),
                                personality = IF(%s != '' AND %s IS NOT NULL, %s, personality),
                                updated_at  = %s
                            WHERE id=%s""",
                            (
                                char.get("role", ""),      char.get("role", ""),      char.get("role", ""),
                                char.get("description",""),char.get("description",""),char.get("description",""),
                                char.get("appearance", ""),char.get("appearance", ""),char.get("appearance", ""),
                                char.get("personality",""),char.get("personality",""),char.get("personality",""),
                                ts, old["id"],
                            ),
                        )
                        self._link_char_to_episode(cur, old["id"])
                        merged += 1
                    else:
                        cur.execute(
                            """INSERT INTO characters
                                (drama_id, name, role, description, appearance, personality, created_at, updated_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (
                                self.drama_id,
                                name,
                                char.get("role", ""),
                                char.get("description", ""),
                                char.get("appearance", ""),
                                char.get("personality", ""),
                                ts, ts,
                            ),
                        )
                        self._link_char_to_episode(cur, cur.lastrowid)
                        created += 1

            conn.commit()

        return {
            "message": f"角色保存完成：新增 {created}，合并更新 {merged}",
            "created": created,
            "merged": merged,
        }

    # ── 5. 保存场景（去重） ───────────────────────────────────

    def save_dedup_scenes(self, scenes: list[dict]) -> dict:
        ts = _now()
        created = reused = 0

        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM scenes WHERE drama_id=%s AND deleted_at IS NULL",
                    (self.drama_id,),
                )
                existing = cur.fetchall()

                for scene in scenes:
                    location = scene["location"]
                    time_val = scene.get("time", "")

                    # 地点 + 时段完全匹配才复用
                    match = next(
                        (s for s in existing if s["location"] == location and s["time"] == time_val),
                        None,
                    )
                    if match:
                        self._link_scene_to_episode(cur, match["id"])
                        reused += 1
                    else:
                        cur.execute(
                            """INSERT INTO scenes
                                (drama_id, location, time, prompt, created_at, updated_at)
                            VALUES (%s,%s,%s,%s,%s,%s)""",
                            (
                                self.drama_id,
                                location,
                                time_val,
                                scene.get("prompt", location),
                                ts, ts,
                            ),
                        )
                        self._link_scene_to_episode(cur, cur.lastrowid)
                        created += 1

            conn.commit()

        return {
            "message": f"场景保存完成：新增 {created}，复用已有 {reused}",
            "created": created,
            "reused": reused,
        }
