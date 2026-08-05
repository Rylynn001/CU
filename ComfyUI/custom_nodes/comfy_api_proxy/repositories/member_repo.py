"""项目成员与角色相关数据库操作"""
from .database import get_db_connection


def get_member_role(project_id: int, user_id: int) -> str | None:
    """返回用户在项目中的角色（owner/admin/member），非成员返回 None"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT role FROM project_members WHERE project_id = %s AND user_id = %s',
            (project_id, user_id)
        )
        row = cursor.fetchone()
        return row['role'] if row else None


def get_roles_for_projects(user_id: int, project_ids: list[int]) -> dict[int, str]:
    """批量查询用户在多个项目中的角色，返回 {project_id: role}"""
    if not project_ids:
        return {}
    with get_db_connection() as conn:
        cursor = conn.cursor()
        ph = ','.join(['%s'] * len(project_ids))
        cursor.execute(
            f'SELECT project_id, role FROM project_members '
            f'WHERE user_id = %s AND project_id IN ({ph})',
            [user_id] + project_ids
        )
        return {row['project_id']: row['role'] for row in cursor.fetchall()}


def list_members(project_id: int) -> list[dict]:
    """列出项目所有成员（含用户名）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT pm.user_id, pm.role, u.user_name
               FROM project_members pm
               LEFT JOIN sys_user u ON u.id = pm.user_id
               WHERE pm.project_id = %s
               ORDER BY FIELD(pm.role, 'owner', 'admin', 'member'), pm.id''',
            (project_id,)
        )
        return cursor.fetchall()


def add_member(project_id: int, user_id: int, role: str = 'member') -> None:
    """添加成员，已存在则忽略"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT IGNORE INTO project_members (project_id, user_id, role, created_at) '
            'VALUES (%s, %s, %s, NOW())',
            (project_id, user_id, role)
        )
        conn.commit()


def set_member_role(project_id: int, user_id: int, role: str) -> bool:
    """更新成员角色，返回是否命中记录"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE project_members SET role = %s WHERE project_id = %s AND user_id = %s',
            (role, project_id, user_id)
        )
        conn.commit()
        if cursor.rowcount > 0:
            return True
        # 角色未变化时 rowcount 也为 0，用存在性判断兜底
        cursor.execute(
            'SELECT 1 FROM project_members WHERE project_id = %s AND user_id = %s',
            (project_id, user_id)
        )
        return cursor.fetchone() is not None


def remove_member(project_id: int, user_id: int) -> bool:
    """移除成员，返回是否删除成功"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM project_members WHERE project_id = %s AND user_id = %s',
            (project_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def find_user_by_name(user_name: str) -> dict | None:
    """按用户名查用户，用于邀请时把用户名解析成 user_id"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, user_name FROM sys_user WHERE user_name = %s', (user_name,))
        return cursor.fetchone()


def list_candidate_users(project_id: int) -> list[dict]:
    """列出尚未加入该项目的所有用户，供选人添加"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT id, user_name FROM sys_user
               WHERE id NOT IN (SELECT user_id FROM project_members WHERE project_id = %s)
               ORDER BY user_name''',
            (project_id,)
        )
        return cursor.fetchall()
