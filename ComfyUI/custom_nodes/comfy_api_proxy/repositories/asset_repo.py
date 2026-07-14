"""资产相关数据库操作"""
from .database import get_db_connection


def ensure_project_sharing_schema() -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS project_members (
            project_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
            role VARCHAR(16) NOT NULL DEFAULT 'viewer', status VARCHAR(16) NOT NULL DEFAULT 'active',
            joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (project_id, user_id), INDEX idx_project_member_user (user_id, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        cursor.execute("SHOW COLUMNS FROM projects LIKE 'updated_at'")
        if not cursor.fetchone(): cursor.execute('ALTER TABLE projects ADD updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')
        conn.commit()


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


def save_input_asset(user_id: int, filename: str, location: str) -> int:
    """写入 input_assets 表，返回新记录 id"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO input_assets (rfid, filename, location) VALUES (%s, %s, %s)',
            (user_id, filename, location)
        )
        conn.commit()
        return cursor.lastrowid


def get_input_asset(asset_id: int) -> dict | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM input_assets WHERE id = %s', (asset_id,))
        return cursor.fetchone()


def get_input_assets_by_ids(asset_ids: list[int]) -> list[dict]:
    if not asset_ids:
        return []
    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join(['%s'] * len(asset_ids))
        cursor.execute(
            f'SELECT id, location FROM input_assets WHERE id IN ({placeholders})',
            asset_ids
        )
        return cursor.fetchall()


def get_user_assets(
    user_id: int,
    asset_type: str | None = None,
    tag: int | None = None,
    favorite_only: bool = False,
    page: int = 1,
    page_size: int = 30,
    query: str | None = None,
    project_id: int | None = None,
    category_id: int | None = None,
    date_range: int | None = None,
) -> tuple[list[dict], int]:
    """分页获取用户资产，返回 (assets, total)

    tag: 精确匹配指定标签（0=未收藏，1=红，2=黄，3=绿，4=蓝）
    favorite_only: 为 True 时匹配任意已收藏颜色（tag > 0），tag 参数优先级更高
    """
    offset = (page - 1) * page_size
    with get_db_connection() as conn:
        cursor = conn.cursor()
        project_match = '''EXISTS (
            SELECT 1 FROM category_assets ca
            JOIN project_category pc ON pc.id = ca.category_id AND pc.del_flag = 0
            JOIN projects p ON p.id = pc.project_id AND p.del_flag = 0
            LEFT JOIN project_members pm ON pm.project_id = p.id AND pm.user_id = %s AND pm.status = 'active'
            WHERE ca.assets_id = assets.id AND (p.user_id = %s OR pm.user_id IS NOT NULL)'''
        if project_id is not None:
            where = f'WHERE {project_match} AND p.id = %s)'
            params: list = [user_id, user_id, project_id]
        else:
            where = 'WHERE rfid = %s'
            params = [user_id]
        if asset_type in ('picture', 'video'):
            where += ' AND asset_type = %s'
            params.append(asset_type)
        if tag is not None:
            where += ' AND tag = %s'
            params.append(tag)
        elif favorite_only:
            where += ' AND tag > 0'
        if date_range in (7, 30):
            where += ' AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)'
            params.append(date_range)
        if category_id is not None:
            where += ' AND EXISTS (SELECT 1 FROM category_assets fc WHERE fc.assets_id = assets.id AND fc.category_id = %s)'
            params.append(category_id)
        if query:
            like = f'%{query}%'
            where += f' AND (location LIKE %s OR {project_match} AND (p.name LIKE %s OR pc.name LIKE %s)))'
            params.extend([like, user_id, user_id, like, like])
        cursor.execute(f'SELECT COUNT(*) AS cnt FROM assets {where}', params)
        total = cursor.fetchone()['cnt']
        cursor.execute(
            f'SELECT id, location, asset_type, tag, created_at FROM assets {where} ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s',
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
    """获取用户所有项目，含分类和资产 id 列表"""
    from collections import defaultdict
    ensure_project_sharing_schema()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''SELECT DISTINCT p.id,p.name,p.user_id,p.updated_at,
            CASE WHEN p.user_id=%s THEN 'personal' ELSE 'shared' END scope,
            CASE WHEN p.user_id=%s THEN 'owner' ELSE pm.role END role,
            1+(SELECT COUNT(*) FROM project_members x WHERE x.project_id=p.id AND x.status='active' AND x.user_id<>p.user_id) member_count
            FROM projects p LEFT JOIN project_members pm ON pm.project_id=p.id AND pm.user_id=%s AND pm.status='active'
            WHERE p.del_flag=0 AND (p.user_id=%s OR pm.user_id=%s) ORDER BY p.updated_at DESC,p.id DESC''',
            (user_id, user_id, user_id, user_id, user_id))
        projects = cursor.fetchall()
        if not projects:
            return []

        project_ids = [p['id'] for p in projects]
        ph = ','.join(['%s'] * len(project_ids))
        cursor.execute(
            f'SELECT id, project_id, name FROM project_category WHERE project_id IN ({ph}) AND del_flag=0 ORDER BY id',
            project_ids
        )
        categories = cursor.fetchall()

        cat_assets: dict[int, list] = defaultdict(list)
        if categories:
            cat_ids = [c['id'] for c in categories]
            ph2 = ','.join(['%s'] * len(cat_ids))
            cursor.execute(
                f'SELECT category_id, assets_id FROM category_assets WHERE category_id IN ({ph2})',
                cat_ids
            )
            for row in cursor.fetchall():
                cat_assets[row['category_id']].append(row['assets_id'])

        proj_cats: dict[int, list] = defaultdict(list)
        for cat in categories:
            proj_cats[cat['project_id']].append({
                'id': cat['id'],
                'name': cat['name'],
                'assets': cat_assets[cat['id']],
            })

        cursor.execute(f'''SELECT pc.project_id,a.id,a.location,a.asset_type,a.created_at
            FROM project_category pc JOIN category_assets ca ON ca.category_id=pc.id
            JOIN assets a ON a.id=ca.assets_id WHERE pc.del_flag=0 AND pc.project_id IN ({ph})
            ORDER BY a.created_at DESC,a.id DESC''', project_ids)
        covers: dict[int, list] = defaultdict(list)
        asset_counts: dict[int, set] = defaultdict(set)
        for row in cursor.fetchall():
            asset_counts[row['project_id']].add(row['id'])
            if len(covers[row['project_id']]) < 3 and row['id'] not in [item['id'] for item in covers[row['project_id']]]:
                covers[row['project_id']].append({key: row[key] for key in ('id','location','asset_type','created_at')})

        return [
            {**p, 'categories': proj_cats[p['id']], 'asset_count': len(asset_counts[p['id']]), 'cover_assets': covers[p['id']]}
            for p in projects
        ]


def get_project_detail(project_id: int, user_id: int) -> dict | None:
    return next((project for project in get_user_projects(user_id) if project['id'] == project_id), None)


def create_project(name: str, user_id: int) -> int:
    ensure_project_sharing_schema()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO projects (name, user_id) VALUES (%s, %s)', (name, user_id))
        project_id = cursor.lastrowid
        conn.commit()
        cursor.execute("INSERT IGNORE INTO project_members (project_id,user_id,role,status) VALUES (%s,%s,'owner','active')", (project_id, user_id))
        conn.commit()
        return project_id


def delete_project(project_id: int, user_id: int) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE projects SET del_flag=1 WHERE id = %s AND user_id = %s', (project_id, user_id))
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
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE projects SET name=%s WHERE id=%s AND user_id=%s AND del_flag=0',
            (name, project_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def rename_category(category_id: int, name: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE project_category SET name=%s WHERE id=%s AND del_flag=0',
            (name, category_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def add_asset_to_category(category_id: int, asset_id: int) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT IGNORE INTO category_assets (assets_id, category_id) VALUES (%s, %s)',
            (asset_id, category_id)
        )
        conn.commit()


def remove_asset_from_category(category_id: int, asset_id: int) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM category_assets WHERE category_id = %s AND assets_id = %s',
            (category_id, asset_id)
        )
        conn.commit()
        return cursor.rowcount > 0
