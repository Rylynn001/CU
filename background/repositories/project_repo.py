"""项目相关数据库操作"""
from typing import Optional
from database import execute_query


# ========== Project 相关操作 ==========

def get_user_projects(user_id: int) -> list[dict]:
    """获取用户的项目列表（含分类统计）"""
    return execute_query(
        '''SELECT p.id, p.name, pm.role, pm.created_at,
                  (SELECT COUNT(*) FROM project_category pc
                   WHERE pc.project_id = p.id AND pc.del_flag = 0) AS category_count
           FROM projects p
           INNER JOIN project_members pm ON p.id = pm.project_id
           WHERE pm.user_id = %s AND p.del_flag = 0
           ORDER BY p.id''',
        (user_id,),
        fetch_all=True
    ) or []


def get_project_by_id(project_id: int) -> Optional[dict]:
    """根据ID获取项目信息"""
    return execute_query(
        'SELECT id, name FROM projects WHERE id = %s AND del_flag = 0',
        (project_id,),
        fetch_one=True
    )


def get_project_member(project_id: int, user_id: int) -> Optional[dict]:
    """获取项目成员信息"""
    return execute_query(
        'SELECT role FROM project_members WHERE project_id = %s AND user_id = %s',
        (project_id, user_id),
        fetch_one=True
    )


def create_project(name: str, owner_id: int) -> int:
    """创建项目并返回项目ID"""
    project_id = execute_query(
        'INSERT INTO projects (name, del_flag) VALUES (%s, 0)',
        (name,)
    )

    # 添加创建者为 owner
    execute_query(
        'INSERT INTO project_members (project_id, user_id, role) VALUES (%s, %s, %s)',
        (project_id, owner_id, 'owner')
    )

    return project_id


def update_project_name(project_id: int, name: str) -> None:
    """更新项目名称"""
    execute_query(
        'UPDATE projects SET name = %s WHERE id = %s',
        (name, project_id)
    )


def delete_project(project_id: int) -> None:
    """删除项目（软删除）"""
    execute_query('UPDATE projects SET del_flag = 1 WHERE id = %s', (project_id,))


# ========== Category 相关操作 ==========

def get_project_categories(project_id: int) -> list[dict]:
    """获取项目的分类列表（含资产统计）"""
    return execute_query(
        '''SELECT pc.id, pc.name,
                  (SELECT COUNT(*) FROM category_assets ca
                   WHERE ca.category_id = pc.id) AS asset_count
           FROM project_category pc
           WHERE pc.project_id = %s AND pc.del_flag = 0
           ORDER BY pc.id''',
        (project_id,),
        fetch_all=True
    ) or []


def create_category(project_id: int, name: str) -> int:
    """创建分类并返回分类ID"""
    return execute_query(
        'INSERT INTO project_category (project_id, name, del_flag) VALUES (%s, %s, 0)',
        (project_id, name)
    )


def update_category_name(category_id: int, name: str) -> None:
    """更新分类名称"""
    execute_query(
        'UPDATE project_category SET name = %s WHERE id = %s',
        (name, category_id)
    )


def delete_category(category_id: int) -> None:
    """删除分类（软删除）"""
    execute_query('UPDATE project_category SET del_flag = 1 WHERE id = %s', (category_id,))


def get_category_assets(category_id: int) -> list[dict]:
    """获取分类下的资产列表"""
    return execute_query(
        '''SELECT a.* FROM assets a
           INNER JOIN category_assets ca ON a.id = ca.assets_id
           WHERE ca.category_id = %s
           ORDER BY ca.created_at DESC''',
        (category_id,),
        fetch_all=True
    ) or []


# ========== Category Assets 相关操作 ==========

def add_asset_to_category(category_id: int, asset_id: int, user_id: int) -> None:
    """添加资产到分类"""
    execute_query(
        '''INSERT INTO category_assets (category_id, assets_id, submitted_by, review_status, created_at)
           VALUES (%s, %s, %s, %s, NOW())''',
        (category_id, asset_id, user_id, 'pending')
    )


def remove_asset_from_category(category_id: int, asset_id: int) -> None:
    """从分类移除资产"""
    execute_query(
        'DELETE FROM category_assets WHERE category_id = %s AND assets_id = %s',
        (category_id, asset_id)
    )


def get_user_pending_assets(user_id: int, page_size: int, offset: int) -> tuple[list[dict], int]:
    """获取用户有权限审核的待审核素材列表及总数"""
    # 总数
    total = execute_query(
        '''SELECT COUNT(*) AS cnt
           FROM category_assets ca
           JOIN project_category pc ON pc.id = ca.category_id
           JOIN projects p ON p.id = pc.project_id
           JOIN project_members pm ON pm.project_id = p.id
           WHERE ca.review_status = 'pending'
             AND pm.user_id = %s
             AND pm.role IN ('owner', 'admin')
             AND p.del_flag = 0
             AND pc.del_flag = 0''',
        (user_id,),
        fetch_one=True
    )['cnt']

    # 列表
    assets = execute_query(
        '''SELECT ca.id, ca.category_id, ca.assets_id, ca.submitted_by, ca.created_at,
                  pc.name AS category_name,
                  p.id AS project_id, p.name AS project_name,
                  a.location, a.asset_type,
                  u.user_name AS submitted_by_name,
                  (SELECT COUNT(*) FROM category_asset_reviews r
                   WHERE r.category_assets_id = ca.id
                     AND r.action = 'reject') AS reject_count
           FROM category_assets ca
           JOIN project_category pc ON pc.id = ca.category_id
           JOIN projects p ON p.id = pc.project_id
           JOIN project_members pm ON pm.project_id = p.id
           LEFT JOIN assets a ON a.id = ca.assets_id
           LEFT JOIN sys_user u ON u.id = ca.submitted_by
           WHERE ca.review_status = 'pending'
             AND pm.user_id = %s
             AND pm.role IN ('owner', 'admin')
             AND p.del_flag = 0
             AND pc.del_flag = 0
           ORDER BY ca.created_at DESC, ca.id DESC
           LIMIT %s OFFSET %s''',
        (user_id, page_size, offset),
        fetch_all=True
    ) or []

    return assets, total


def get_user_submissions(user_id: int, page_size: int, offset: int) -> tuple[list[dict], int, int]:
    """获取用户提交的素材列表及总数、被驳回总数"""
    # 总数和被驳回数
    counts = execute_query(
        '''SELECT COUNT(*) AS cnt,
                  COALESCE(SUM(CASE WHEN ca.review_status = 'rejected' THEN 1 ELSE 0 END), 0) AS rejected_count
           FROM category_assets ca
           JOIN project_category pc ON pc.id = ca.category_id
           JOIN projects p ON p.id = pc.project_id
           WHERE ca.submitted_by = %s AND pc.del_flag = 0 AND p.del_flag = 0''',
        (user_id,),
        fetch_one=True
    )

    # 列表
    submissions = execute_query(
        '''SELECT ca.id, ca.category_id, ca.assets_id, ca.review_status, ca.created_at,
                  pc.name AS category_name,
                  p.id AS project_id, p.name AS project_name,
                  a.location, a.asset_type,
                  (SELECT COUNT(*) FROM category_asset_reviews r
                   WHERE r.category_assets_id = ca.id
                     AND r.action = 'reject') AS reject_count
           FROM category_assets ca
           JOIN project_category pc ON pc.id = ca.category_id
           JOIN projects p ON p.id = pc.project_id
           LEFT JOIN assets a ON a.id = ca.assets_id
           WHERE ca.submitted_by = %s AND pc.del_flag = 0 AND p.del_flag = 0
           ORDER BY ca.created_at DESC, ca.id DESC
           LIMIT %s OFFSET %s''',
        (user_id, page_size, offset),
        fetch_all=True
    ) or []

    return submissions, counts['cnt'], counts['rejected_count']


# ========== Project Members 相关操作 ==========

def get_project_members(project_id: int) -> list[dict]:
    """获取项目成员列表"""
    return execute_query(
        '''SELECT pm.user_id, pm.role, pm.created_at,
                  u.user_name AS username
           FROM project_members pm
           LEFT JOIN sys_user u ON u.id = pm.user_id
           WHERE pm.project_id = %s
           ORDER BY pm.created_at''',
        (project_id,),
        fetch_all=True
    ) or []


def add_project_member(project_id: int, user_id: int, role: str) -> None:
    """添加项目成员"""
    execute_query(
        'INSERT INTO project_members (project_id, user_id, role, created_at) VALUES (%s, %s, %s, NOW())',
        (project_id, user_id, role)
    )


def check_project_member_exists(project_id: int, user_id: int) -> bool:
    """检查用户是否已是项目成员"""
    result = execute_query(
        'SELECT id FROM project_members WHERE project_id = %s AND user_id = %s',
        (project_id, user_id),
        fetch_one=True
    )
    return result is not None


def update_project_member_role(project_id: int, user_id: int, role: str) -> None:
    """更新项目成员角色"""
    execute_query(
        'UPDATE project_members SET role = %s WHERE project_id = %s AND user_id = %s',
        (role, project_id, user_id)
    )


def remove_project_member(project_id: int, user_id: int) -> None:
    """移除项目成员"""
    execute_query(
        'DELETE FROM project_members WHERE project_id = %s AND user_id = %s',
        (project_id, user_id)
    )


# ========== User 相关操作 ==========

def get_user_by_username(username: str) -> Optional[dict]:
    """根据用户名获取用户信息"""
    return execute_query(
        'SELECT id, user_name FROM sys_user WHERE user_name = %s',
        (username,),
        fetch_one=True
    )


def get_candidate_users(project_id: int, keyword: str, page_size: int, offset: int) -> tuple[list[dict], int]:
    """获取可添加的候选用户（未加入该项目的用户）"""
    base_condition = '''WHERE u.id NOT IN (
        SELECT user_id FROM project_members WHERE project_id = %s
    )'''
    params = [project_id]

    # 如果有搜索关键字，添加模糊查询
    if keyword.strip():
        base_condition += ' AND (u.real_name LIKE %s OR u.user_name LIKE %s)'
        like_pattern = f'%{keyword.strip()}%'
        params.extend([like_pattern, like_pattern])

    # 查询总数
    total_row = execute_query(
        f'SELECT COUNT(*) as total FROM sys_user u {base_condition}',
        tuple(params),
        fetch_one=True
    )
    total = total_row['total'] if total_row else 0

    # 查询分页数据
    users = execute_query(
        f'''SELECT u.id, u.user_name, u.real_name
           FROM sys_user u
           {base_condition}
           ORDER BY u.real_name
           LIMIT %s OFFSET %s''',
        tuple(params + [page_size, offset]),
        fetch_all=True
    ) or []

    return users, total


# ========== Review 相关操作 ==========

def get_category_asset_record(category_id: int, asset_id: int) -> Optional[dict]:
    """获取分类资产记录及项目ID"""
    return execute_query(
        '''SELECT ca.id, ca.review_status, p.id AS project_id
           FROM category_assets ca
           JOIN categories c ON c.id = ca.category_id
           JOIN projects p ON p.id = c.project_id
           WHERE ca.category_id = %s AND ca.assets_id = %s''',
        (category_id, asset_id),
        fetch_one=True
    )


def update_asset_review_status(category_id: int, asset_id: int, new_status: str) -> None:
    """更新资产审核状态"""
    execute_query(
        'UPDATE category_assets SET review_status = %s WHERE category_id = %s AND assets_id = %s',
        (new_status, category_id, asset_id)
    )


def create_asset_review_record(category_assets_id: int, reviewer_id: int,
                                action: str, comment: str | None) -> None:
    """创建资产审核记录"""
    execute_query(
        '''INSERT INTO category_asset_reviews (category_assets_id, reviewer_id, action, comment, created_at)
           VALUES (%s, %s, %s, %s, NOW())''',
        (category_assets_id, reviewer_id, action, comment)
    )


def get_asset_review_timeline(category_id: int, asset_id: int) -> Optional[tuple[dict, list[dict]]]:
    """获取资产的审核时间线信息"""
    # 获取基本信息
    info = execute_query(
        '''SELECT ca.id, pc.project_id, ca.submitted_by
           FROM project_category pc
           JOIN category_assets ca ON ca.category_id = pc.id
           WHERE pc.id = %s AND ca.assets_id = %s''',
        (category_id, asset_id),
        fetch_one=True
    )

    if not info:
        return None

    # 查询审核时间线
    reviews = execute_query(
        '''SELECT r.action, r.comment, r.reviewer_id, r.created_at,
                  u.user_name AS reviewer_name,
                  r.assets_id,
                  a.location, a.asset_type
           FROM category_asset_reviews r
           LEFT JOIN sys_user u ON u.id = r.reviewer_id
           LEFT JOIN assets a ON a.id = r.assets_id
           WHERE r.category_assets_id = %s
           ORDER BY r.created_at ASC, r.id ASC''',
        (info['id'],),
        fetch_all=True
    ) or []

    return info, reviews


def get_member_role_in_category_project(category_id: int, user_id: int) -> Optional[dict]:
    """获取用户在分类所属项目中的角色"""
    return execute_query(
        '''SELECT pm.role FROM project_members pm
           INNER JOIN project_category c ON pm.project_id = c.project_id
           WHERE c.id = %s AND pm.user_id = %s''',
        (category_id, user_id),
        fetch_one=True
    )
