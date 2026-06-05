"""
extract_tools 测试 — 连接真实 MySQL，写测试通过事务回滚隔离，不污染数据
读测试直接查真实数据（drama_id=1, episode_id=1）
"""
import pytest
import pymysql
import pymysql.cursors
from tools import ExtractTools, DEFAULT_DB_CONFIG


# ── 连接配置 ─────────────────────────────────────────────────

DB_CONFIG = DEFAULT_DB_CONFIG.copy()


def raw_conn():
    """返回一个不自动提交的裸连接，用于测试隔离"""
    cfg = {**DB_CONFIG, "autocommit": False}
    return pymysql.connect(**cfg)


# ── 写测试专用 fixture：每个测试独立事务，结束后回滚 ─────────

@pytest.fixture
def isolated(request):
    """
    提供一个在事务内运行的 ExtractTools。
    测试结束后无论成功/失败都 ROLLBACK，真实表不会有任何残留。
    通过 monkeypatch 让 ExtractTools._conn() 始终返回同一个连接。
    """
    conn = raw_conn()

    class IsolatedTools(ExtractTools):
        def _conn(self):
            # 返回已开启事务的连接，不新建
            return _PatchedConn(conn)

    tools = IsolatedTools(episode_id=1, drama_id=1, db_config=DB_CONFIG)
    yield tools, conn
    conn.rollback()
    conn.close()


class _PatchedConn:
    """包装真实连接，让 with 语句不关闭/不提交（测试结束后由 fixture 统一 rollback）"""
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self  # 必须返回 self，才能拦截 commit()

    def __exit__(self, *args):
        pass  # 不关闭，不提交

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        pass  # 禁止提交，保证事务隔离


# ── 读测试（直连真实库，只查不写）────────────────────────────

@pytest.fixture
def seeded(isolated):
    """在隔离事务中预插 drama + episode，返回 (tools, conn, drama_id, episode_id)"""
    tools, conn = isolated
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dramas (title, status, created_at, updated_at) VALUES (%s,%s,%s,%s)",
            ("__测试剧__", "draft", "2024-01-01", "2024-01-01"),
        )
        drama_id = cur.lastrowid
        cur.execute(
            """INSERT INTO episodes (drama_id, episode_number, title, script_content, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (drama_id, 1, "__第一集__", "李明走进咖啡厅，见到了张薇。", "2024-01-01", "2024-01-01"),
        )
        episode_id = cur.lastrowid
    tools.drama_id = drama_id
    tools.episode_id = episode_id
    return tools, conn, drama_id, episode_id


class TestReadScript:
    def test_returns_script(self, seeded):
        tools, conn, drama_id, episode_id = seeded
        result = tools.read_script_for_extraction()
        assert "script" in result, f"期望 script 字段，实际: {result}"
        assert "李明" in result["script"]

    def test_missing_episode(self, isolated):
        tools, conn = isolated
        tools.episode_id = 999999
        result = tools.read_script_for_extraction()
        assert result == {"error": "Episode not found"}

    def test_no_script_content(self, isolated):
        """episode 有记录但 script_content 和 content 都为空"""
        tools, conn = isolated
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dramas (title, status, created_at, updated_at) VALUES (%s,%s,%s,%s)",
                ("__空剧__", "draft", "2024-01-01", "2024-01-01"),
            )
            drama_id = cur.lastrowid
            cur.execute(
                "INSERT INTO episodes (drama_id, episode_number, title, created_at, updated_at) VALUES (%s,%s,%s,%s,%s)",
                (drama_id, 1, "__空集__", "2024-01-01", "2024-01-01"),
            )
            tools.episode_id = cur.lastrowid
            tools.drama_id = drama_id
        result = tools.read_script_for_extraction()
        assert result == {"error": "Episode has no script content"}


class TestReadExistingCharacters:
    def test_empty(self, seeded):
        tools, conn, drama_id, episode_id = seeded
        result = tools.read_existing_characters()
        assert result["count"] == 0
        assert result["current_episode_characters"] == []

    def test_with_linked_character(self, seeded):
        tools, conn, drama_id, episode_id = seeded
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO characters (drama_id, name, role, created_at, updated_at) VALUES (%s,%s,%s,%s,%s)",
                (drama_id, "__已关联角色__", "主角", "2024-01-01", "2024-01-01"),
            )
            char_id = cur.lastrowid
            cur.execute(
                "INSERT INTO episode_characters (episode_id, character_id, created_at) VALUES (%s,%s,%s)",
                (episode_id, char_id, "2024-01-01"),
            )
        result = tools.read_existing_characters()
        assert result["count"] == 1
        assert len(result["current_episode_characters"]) == 1
        assert result["current_episode_characters"][0]["name"] == "__已关联角色__"

    def test_episode_chars_subset_of_all(self, seeded):
        tools, conn, drama_id, episode_id = seeded
        result = tools.read_existing_characters()
        all_ids = {c["id"] for c in result["characters"]}
        ep_ids = {c["id"] for c in result["current_episode_characters"]}
        assert ep_ids.issubset(all_ids)


class TestReadExistingScenes:
    def test_empty(self, seeded):
        tools, conn, drama_id, episode_id = seeded
        result = tools.read_existing_scenes()
        assert result["count"] == 0
        assert result["current_episode_scenes"] == []

    def test_with_linked_scene(self, seeded):
        tools, conn, drama_id, episode_id = seeded
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scenes (drama_id, location, time, prompt, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (drama_id, "__已关联地点__", "下午", "test", "2024-01-01", "2024-01-01"),
            )
            scene_id = cur.lastrowid
            cur.execute(
                "INSERT INTO episode_scenes (episode_id, scene_id, created_at) VALUES (%s,%s,%s)",
                (episode_id, scene_id, "2024-01-01"),
            )
        result = tools.read_existing_scenes()
        assert result["count"] == 1
        assert len(result["current_episode_scenes"]) == 1

    def test_episode_scenes_subset_of_all(self, seeded):
        tools, conn, drama_id, episode_id = seeded
        result = tools.read_existing_scenes()
        all_ids = {s["id"] for s in result["scenes"]}
        ep_ids = {s["id"] for s in result["current_episode_scenes"]}
        assert ep_ids.issubset(all_ids)


# ── 写测试（事务隔离，全部回滚）─────────────────────────────

class TestSaveDedupCharacters:
    def test_create_new_characters(self, seeded):
        tools, conn, drama_id, episode_id = seeded
        result = tools.save_dedup_characters([
            {"name": "__测试角色A__", "role": "主角", "appearance": "高挑"},
            {"name": "__测试角色B__", "role": "配角"},
        ])
        assert result["created"] == 2
        assert result["merged"] == 0

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM characters WHERE name IN ('__测试角色A__','__测试角色B__')")
            assert cur.fetchone()["cnt"] == 2

    def test_merge_existing_character(self, seeded):
        """同名角色应合并，不新建"""
        tools, conn, drama_id, episode_id = seeded
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO characters (drama_id, name, role, created_at, updated_at) VALUES (%s,%s,%s,%s,%s)",
                (drama_id, "__合并测试__", "配角", "2024-01-01", "2024-01-01"),
            )
        result = tools.save_dedup_characters([
            {"name": "__合并测试__", "role": "主角", "appearance": "新外貌"}
        ])
        assert result["created"] == 0
        assert result["merged"] == 1

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM characters WHERE name='__合并测试__' AND drama_id=%s", (drama_id,))
            assert cur.fetchone()["cnt"] == 1

    def test_no_duplicate_episode_link(self, seeded):
        """重复调用不应重复插入 episode_characters"""
        tools, conn, drama_id, episode_id = seeded
        tools.save_dedup_characters([{"name": "__重复关联测试__", "role": "主角"}])
        tools.save_dedup_characters([{"name": "__重复关联测试__", "role": "主角"}])

        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as cnt FROM episode_characters WHERE episode_id=%s AND character_id IN "
                "(SELECT id FROM characters WHERE name='__重复关联测试__')",
                (episode_id,),
            )
            assert cur.fetchone()["cnt"] == 1

    def test_episode_link_created(self, seeded):
        """新建角色后应自动关联到当前集"""
        tools, conn, drama_id, episode_id = seeded
        tools.save_dedup_characters([{"name": "__关联测试__", "role": "主角"}])

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM characters WHERE name='__关联测试__' AND drama_id=%s", (drama_id,))
            char = cur.fetchone()
            assert char is not None
            cur.execute(
                "SELECT id FROM episode_characters WHERE episode_id=%s AND character_id=%s",
                (episode_id, char["id"]),
            )
            assert cur.fetchone() is not None


class TestSaveDedupScenes:
    def test_create_new_scenes(self, seeded):
        tools, conn, drama_id, episode_id = seeded
        result = tools.save_dedup_scenes([
            {"location": "__测试地点A__", "time": "清晨", "prompt": "test scene A"},
            {"location": "__测试地点B__", "time": "夜晚", "prompt": "test scene B"},
        ])
        assert result["created"] == 2
        assert result["reused"] == 0

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM scenes WHERE location IN ('__测试地点A__','__测试地点B__')")
            assert cur.fetchone()["cnt"] == 2

    def test_reuse_exact_match(self, seeded):
        """地点+时段完全相同时复用，不新建"""
        tools, conn, drama_id, episode_id = seeded
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scenes (drama_id, location, time, prompt, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (drama_id, "__复用地点__", "傍晚", "existing prompt", "2024-01-01", "2024-01-01"),
            )
        result = tools.save_dedup_scenes([
            {"location": "__复用地点__", "time": "傍晚", "prompt": "new prompt"}
        ])
        assert result["created"] == 0
        assert result["reused"] == 1

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM scenes WHERE location='__复用地点__'")
            assert cur.fetchone()["cnt"] == 1

    def test_same_location_different_time(self, seeded):
        """同地点不同时段应新建独立场景"""
        tools, conn, drama_id, episode_id = seeded
        tools.save_dedup_scenes([{"location": "__同地点__", "time": "清晨"}])
        result = tools.save_dedup_scenes([{"location": "__同地点__", "time": "深夜"}])
        assert result["created"] == 1

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM scenes WHERE location='__同地点__'")
            assert cur.fetchone()["cnt"] == 2

    def test_default_prompt_uses_location(self, seeded):
        """没有提供 prompt 时默认使用 location"""
        tools, conn, drama_id, episode_id = seeded
        tools.save_dedup_scenes([{"location": "__无提示词地点__"}])

        with conn.cursor() as cur:
            cur.execute("SELECT prompt FROM scenes WHERE location='__无提示词地点__'")
            row = cur.fetchone()
            assert row["prompt"] == "__无提示词地点__"

    def test_episode_link_created(self, seeded):
        """新建场景后应自动关联到当前集"""
        tools, conn, drama_id, episode_id = seeded
        tools.save_dedup_scenes([{"location": "__场景关联测试__", "time": "黄昏"}])

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM scenes WHERE location='__场景关联测试__' AND drama_id=%s", (drama_id,))
            scene = cur.fetchone()
            assert scene is not None
            cur.execute(
                "SELECT id FROM episode_scenes WHERE episode_id=%s AND scene_id=%s",
                (episode_id, scene["id"]),
            )
            assert cur.fetchone() is not None


# ── 完整流程集成测试 ──────────────────────────────────────────

class TestFullFlow:
    def test_full_extraction_flow(self, seeded):
        """模拟 Agent 完整调用链：读剧本 → 读已有 → 保存"""
        tools, conn, drama_id, episode_id = seeded

        # 步骤 1：读剧本
        script_result = tools.read_script_for_extraction()
        assert "script" in script_result

        # 步骤 2-3：读取已有（隔离事务中没有测试数据）
        before_chars = tools.read_existing_characters()
        before_scenes = tools.read_existing_scenes()

        # 步骤 4-5：保存提取结果
        char_result = tools.save_dedup_characters([
            {"name": "__集成测试角色__", "role": "主角", "appearance": "高挑男性"},
        ])
        scene_result = tools.save_dedup_scenes([
            {"location": "__集成测试地点__", "time": "下午", "prompt": "integration test scene"},
        ])

        assert char_result["created"] == 1
        assert scene_result["created"] == 1

        # 验证关联
        after_chars = tools.read_existing_characters()
        after_scenes = tools.read_existing_scenes()

        new_ep_chars = [c for c in after_chars["current_episode_characters"] if c["name"] == "__集成测试角色__"]
        new_ep_scenes = [s for s in after_scenes["current_episode_scenes"] if s["location"] == "__集成测试地点__"]

        assert len(new_ep_chars) == 1
        assert len(new_ep_scenes) == 1
