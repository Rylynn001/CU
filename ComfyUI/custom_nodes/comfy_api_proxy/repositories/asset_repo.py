"""资产相关数据库操作"""
from .database import get_db_connection


def save_output_asset(location: str, user_id: int, asset_type: str) -> int:
    """写入 assets 表，返回新记录 id"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO assets (location, rfid, asset_type, created_at) VALUES (%s, %s, %s, NOW())',
            (location, user_id, asset_type)
        )
        conn.commit()
        return cursor.lastrowid



def get_user_assets(
    user_id: int,
    asset_type: str | None = None,
    tag: int | None = None,
    favorite_only: bool = False,
    page: int = 1,
    page_size: int = 30,
) -> tuple[list[dict], int]:
    """分页获取用户资产，返回 (assets, total)

    tag: 精确匹配指定标签（0=未收藏，1=红，2=黄，3=绿，4=蓝）
    favorite_only: 为 True 时匹配任意已收藏颜色（tag > 0），tag 参数优先级更高
    """
    offset = (page - 1) * page_size
    with get_db_connection() as conn:
        cursor = conn.cursor()
        where = 'WHERE rfid = %s'
        params: list = [user_id]
        if asset_type in ('picture', 'video'):
            where += ' AND asset_type = %s'
            params.append(asset_type)
        if tag is not None:
            where += ' AND tag = %s'
            params.append(tag)
        elif favorite_only:
            where += ' AND tag > 0'
        cursor.execute(f'SELECT COUNT(*) AS cnt FROM assets {where}', params)
        total = cursor.fetchone()['cnt']
        cursor.execute(
            f'SELECT id, location, asset_type, tag FROM assets {where} ORDER BY id DESC LIMIT %s OFFSET %s',
            params + [page_size, offset]
        )
        return cursor.fetchall(), total


def set_asset_tag(asset_id: int, user_id: int, tag: int) -> bool:
    """设置资产 tag（0=未收藏，1=红，2=黄，3=绿，4=蓝），返回是否成功"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE assets SET tag = %s WHERE id = %s AND rfid = %s',
            (tag, asset_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def get_asset_by_id(asset_id: int) -> dict | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, location, rfid, asset_type FROM assets WHERE id = %s', (asset_id,))
        return cursor.fetchone()


def find_asset_by_filename(filename: str, user_id: int) -> dict | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM assets WHERE location LIKE %s AND rfid = %s ORDER BY id DESC LIMIT 1",
            (f'%{filename}', user_id)
        )
        return cursor.fetchone()


def get_assets_by_ids(asset_ids: list[int]) -> list[dict]:
    if not asset_ids:
        return []
    with get_db_connection() as conn:
        cursor = conn.cursor()
        ph = ','.join(['%s'] * len(asset_ids))
        cursor.execute(
            f'SELECT id, location, asset_type, tag FROM assets WHERE id IN ({ph})',
            asset_ids
        )
        return cursor.fetchall()


# ── 项目 ──────────────────────────────────────────────────────────────────

def get_user_projects(user_id: int) -> list[dict]:
    """获取用户参与的所有项目（仅项目本身，含分类数量）

    分类和资产按需加载：点击项目查分类，点击分类查资产。
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT p.id, p.name, pm.role,
                      (SELECT COUNT(*) FROM project_category pc
                       WHERE pc.project_id = p.id AND pc.del_flag = 0) AS category_count
               FROM projects p
               JOIN project_members pm ON pm.project_id = p.id
               WHERE pm.user_id = %s AND p.del_flag = 0
               ORDER BY p.id''',
            (user_id,)
        )
        return [
            {'id': p['id'], 'name': p['name'], 'role': p['role'], 'category_count': p['category_count']}
            for p in cursor.fetchall()
        ]


def get_project_categories(project_id: int, user_id: int) -> list[dict] | None:
    """获取项目下分类列表（含各分类 approved 资产数量）。

    仅项目成员可查，非成员返回 None。
    """
    from . import member_repo
    if member_repo.get_member_role(project_id, user_id) is None:
        return None
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT pc.id, pc.name,
                      (SELECT COUNT(*) FROM category_assets ca
                       WHERE ca.category_id = pc.id AND ca.review_status = 'approved') AS asset_count
               FROM project_category pc
               WHERE pc.project_id = %s AND pc.del_flag = 0
               ORDER BY pc.id''',
            (project_id,)
        )
        return [
            {'id': c['id'], 'name': c['name'], 'asset_count': c['asset_count']}
            for c in cursor.fetchall()
        ]


def get_category_assets(category_id: int) -> list[dict]:
    """获取分类下已通过审核（approved）的资产完整信息。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT a.id, a.location, a.asset_type, a.tag
               FROM category_assets ca
               JOIN assets a ON a.id = ca.assets_id
               WHERE ca.category_id = %s AND ca.review_status = 'approved'
               ORDER BY ca.assets_id DESC''',
            (category_id,)
        )
        return cursor.fetchall()


def create_project(name: str, user_id: int) -> dict:
    with get_db_connection() as conn:
        objs = ['人物','场景','道具']
        cursor = conn.cursor()
        cursor.execute('INSERT INTO projects (name, user_id) VALUES (%s, %s)', (name, user_id))
        lastrowid = cursor.lastrowid
        # 创建者即项目 owner
        cursor.execute(
            'INSERT INTO project_members (project_id, user_id, role) VALUES (%s, %s, %s)',
            (lastrowid, user_id, 'owner')
        )
        categories = []
        for obj in objs:
            sql = "insert into project_category (project_id, name) VALUES (%s, %s)"
            cursor.execute(sql, (lastrowid, obj))
            categories.append({'id': cursor.lastrowid, 'name': obj, 'assets': []})
        conn.commit()
        return {'id': lastrowid, 'categories': categories}


def delete_project(project_id: int, user_id: int) -> bool:
    """删除项目，仅 owner 可操作"""
    from . import member_repo
    if member_repo.get_member_role(project_id, user_id) != 'owner':
        return False
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE projects SET del_flag=1 WHERE id = %s AND del_flag=0', (project_id,))
        conn.commit()
        return cursor.rowcount > 0


def create_category(project_id: int, name: str) -> int:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO project_category (project_id, name) VALUES (%s, %s)', (project_id, name))
        conn.commit()
        return cursor.lastrowid


def delete_category(category_id: int) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE project_category SET del_flag=1 WHERE id = %s', (category_id,))
        conn.commit()
        return cursor.rowcount > 0


def rename_project(project_id: int, user_id: int, name: str) -> bool:
    """重命名项目，owner/admin 可操作"""
    from . import member_repo
    if member_repo.get_member_role(project_id, user_id) not in ('owner', 'admin'):
        return False
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE projects SET name=%s WHERE id=%s AND del_flag=0',
            (name, project_id)
        )
        conn.commit()
        # MyISAM 在名称未变化时 rowcount=0，此处已通过权限校验且项目存在，视为成功
        return True


def rename_category(category_id: int, name: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE project_category SET name=%s WHERE id=%s AND del_flag=0',
            (name, category_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def add_asset_to_category(category_id: int, asset_id: int, user_id: int) -> str | None:
    """提交素材到分类。owner/admin 直接通过，member 进入待审核。
    已被驳回的素材允许重新提交（状态改回 pending）。
    返回 review_status（'approved'/'pending'）；非成员返回 None。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # 通过分类反查项目，再查提交人在该项目的角色
        cursor.execute(
            '''SELECT pm.role
               FROM project_category pc
               JOIN project_members pm ON pm.project_id = pc.project_id
               WHERE pc.id = %s AND pm.user_id = %s''',
            (category_id, user_id)
        )
        row = cursor.fetchone()
        if not row:
            return None
        review_status = 'approved' if row['role'] in ('owner', 'admin') else 'pending'
        # 查是否已有关联行
        cursor.execute(
            'SELECT review_status FROM category_assets WHERE category_id = %s AND assets_id = %s',
            (category_id, asset_id)
        )
        existing = cursor.fetchone()
        if existing:
            # 已通过或待审核的直接返回现状，不重复提交
            if existing['review_status'] in ('approved', 'pending'):
                return existing['review_status']
            # 被驳回的重新提交：状态改回本次判定结果
            cursor.execute(
                '''UPDATE category_assets
                   SET review_status = %s, submitted_by = %s, created_at = NOW()
                   WHERE category_id = %s AND assets_id = %s''',
                (review_status, user_id, category_id, asset_id)
            )
        else:
            cursor.execute(
                '''INSERT INTO category_assets
                   (assets_id, category_id, submitted_by, review_status, created_at)
                   VALUES (%s, %s, %s, %s, NOW())''',
                (asset_id, category_id, user_id, review_status)
            )
        # 记录提交事件
        cursor.execute(
            '''INSERT INTO category_asset_reviews
               (category_id, assets_id, action, reviewer_id, created_at)
               VALUES (%s, %s, 'submit', %s, NOW())''',
            (category_id, asset_id, user_id)
        )
        conn.commit()
        return review_status


def list_pending_assets(project_id: int, user_id: int) -> list[dict] | None:
    """列出项目下待审核素材，仅 owner/admin 可查。无权限返回 None。
    附带该素材在此分类历史上被驳回的次数 reject_count。"""
    from . import member_repo
    if member_repo.get_member_role(project_id, user_id) not in ('owner', 'admin'):
        return None
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT ca.category_id, ca.assets_id, ca.submitted_by, ca.created_at,
                      pc.name AS category_name, a.location, a.asset_type,
                      (SELECT COUNT(*) FROM category_asset_reviews r
                       WHERE r.category_id = ca.category_id AND r.assets_id = ca.assets_id
                         AND r.action = 'reject') AS reject_count
               FROM category_assets ca
               JOIN project_category pc ON pc.id = ca.category_id
               LEFT JOIN assets a ON a.id = ca.assets_id
               WHERE pc.project_id = %s AND ca.review_status = 'pending'
               ORDER BY ca.created_at DESC''',
            (project_id,)
        )
        rows = cursor.fetchall()
    for r in rows:
        if r.get('created_at'):
            r['created_at'] = r['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    return rows


def review_asset(category_id: int, asset_id: int, user_id: int, approve: bool, comment: str | None = None) -> bool:
    """审核素材。owner/admin 可操作：通过置 approved，驳回置 rejected（不删行）。
    每次审核都写入历史，通过和驳回均可附评语。"""
    from . import member_repo
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # 反查项目并校验审核人角色
        cursor.execute(
            '''SELECT pm.role
               FROM project_category pc
               JOIN project_members pm ON pm.project_id = pc.project_id
               WHERE pc.id = %s AND pm.user_id = %s''',
            (category_id, user_id)
        )
        row = cursor.fetchone()
        if not row or row['role'] not in ('owner', 'admin'):
            return False
        new_status = 'approved' if approve else 'rejected'
        cursor.execute(
            '''UPDATE category_assets SET review_status = %s, reviewed_by = %s
               WHERE category_id = %s AND assets_id = %s AND review_status = 'pending' ''',
            (new_status, user_id, category_id, asset_id)
        )
        if cursor.rowcount == 0:
            return False
        cursor.execute(
            '''INSERT INTO category_asset_reviews
               (category_id, assets_id, action, comment, reviewer_id, created_at)
               VALUES (%s, %s, %s, %s, %s, NOW())''',
            (category_id, asset_id, 'approve' if approve else 'reject', comment, user_id)
        )
        conn.commit()
        return True


def get_asset_review_timeline(category_id: int, asset_id: int, user_id: int) -> list[dict] | None:
    """查某素材在某分类的审核时间线。owner/admin 或提交人本人可查，否则 None。"""
    from . import member_repo
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # 反查项目 id 与提交人，用于权限判断
        cursor.execute(
            '''SELECT pc.project_id, ca.submitted_by
               FROM project_category pc
               JOIN category_assets ca ON ca.category_id = pc.id
               WHERE pc.id = %s AND ca.assets_id = %s''',
            (category_id, asset_id)
        )
        info = cursor.fetchone()
        if not info:
            return None
        role = member_repo.get_member_role(info['project_id'], user_id)
        if role not in ('owner', 'admin') and info['submitted_by'] != user_id:
            return None
        cursor.execute(
            '''SELECT r.action, r.comment, r.reviewer_id, r.created_at, u.user_name AS reviewer_name
               FROM category_asset_reviews r
               LEFT JOIN sys_user u ON u.id = r.reviewer_id
               WHERE r.category_id = %s AND r.assets_id = %s
               ORDER BY r.created_at ASC, r.id ASC''',
            (category_id, asset_id)
        )
        rows = cursor.fetchall()
    for r in rows:
        if r.get('created_at'):
            r['created_at'] = r['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    return rows


def list_my_submissions(project_id: int, user_id: int) -> list[dict]:
    """列出当前用户在项目下提交的素材及其当前状态与被驳回次数。
    用于成员查看自己的提交进度（含被驳回的）。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT ca.category_id, ca.assets_id, ca.review_status, ca.created_at,
                      pc.name AS category_name, a.location, a.asset_type,
                      (SELECT COUNT(*) FROM category_asset_reviews r
                       WHERE r.category_id = ca.category_id AND r.assets_id = ca.assets_id
                         AND r.action = 'reject') AS reject_count
               FROM category_assets ca
               JOIN project_category pc ON pc.id = ca.category_id
               LEFT JOIN assets a ON a.id = ca.assets_id
               WHERE pc.project_id = %s AND ca.submitted_by = %s AND pc.del_flag = 0
               ORDER BY ca.created_at DESC''',
            (project_id, user_id)
        )
        rows = cursor.fetchall()
    for r in rows:
        if r.get('created_at'):
            r['created_at'] = r['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    return rows


def remove_asset_from_category(category_id: int, asset_id: int) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM category_assets WHERE category_id = %s AND assets_id = %s',
            (category_id, asset_id)
        )
        conn.commit()
        return cursor.rowcount > 0
