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
    """获取用户所有项目，含分类和资产 id 列表"""
    from collections import defaultdict
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name FROM projects WHERE user_id = %s AND del_flag=0 ORDER BY id', (user_id,))
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
                f'SELECT category_id, assets_id FROM assets_category WHERE category_id IN ({ph2})',
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

        return [
            {'id': p['id'], 'name': p['name'], 'categories': proj_cats[p['id']]}
            for p in projects
        ]


def create_project(name: str, user_id: int) -> int:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO projects (name, user_id) VALUES (%s, %s)', (name, user_id))
        conn.commit()
        return cursor.lastrowid


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
            'INSERT IGNORE INTO assets_category (assets_id, category_id) VALUES (%s, %s)',
            (asset_id, category_id)
        )
        conn.commit()


def remove_asset_from_category(category_id: int, asset_id: int) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM assets_category WHERE category_id = %s AND assets_id = %s',
            (category_id, asset_id)
        )
        conn.commit()
        return cursor.rowcount > 0
