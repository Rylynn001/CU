"""资产相关的数据库操作"""
from database import execute_query


def save_output_asset(location: str, user_id: int, asset_type: str) -> int:
    """写入 assets 表，返回新记录 id"""
    asset_id = execute_query(
        'INSERT INTO assets (location, rfid, asset_type, created_at) VALUES (%s, %s, %s, NOW())',
        (location, user_id, asset_type)
    )
    return asset_id


def get_user_assets(user_id: int, asset_type: str | None, tag: int | None, favorite: bool, page: int, page_size: int):
    """获取用户资产列表"""
    offset = (page - 1) * page_size
    conditions = ['rfid = %s']
    params = [user_id]

    if asset_type in ('picture', 'video'):
        conditions.append('asset_type = %s')
        params.append(asset_type)

    if tag is not None:
        conditions.append('tag = %s')
        params.append(tag)

    if favorite:
        conditions.append('tag > 0')

    where_clause = ' AND '.join(conditions)

    # 查询总数
    total = execute_query(
        f'SELECT COUNT(*) as cnt FROM assets WHERE {where_clause}',
        tuple(params),
        fetch_one=True
    )['cnt']

    # 查询数据
    assets = execute_query(
        f'SELECT * FROM assets WHERE {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s',
        tuple(params + [page_size, offset]),
        fetch_all=True
    ) or []

    return assets, total


def update_asset_tag(asset_id: int, user_id: int, tag: int):
    """更新资产标签"""
    result = execute_query(
        'UPDATE assets SET tag = %s WHERE id = %s AND rfid = %s',
        (tag, asset_id, user_id)
    )
    return result


def create_asset(location: str, user_id: int, asset_type: str):
    """创建资产记录"""
    asset_id = execute_query(
        'INSERT INTO assets (location, rfid, asset_type, created_at) VALUES (%s, %s, %s, NOW())',
        (location, user_id, asset_type)
    )
    return asset_id


def get_assets_by_ids(ids: list[int]):
    """批量获取资产"""
    if not ids:
        return []

    placeholders = ','.join(['%s'] * len(ids))
    assets = execute_query(
        f'SELECT * FROM assets WHERE id IN ({placeholders})',
        tuple(ids),
        fetch_all=True
    ) or []
    return assets


def get_asset_by_id(asset_id: int):
    """根据ID获取资产"""
    asset = execute_query(
        'SELECT * FROM assets WHERE id = %s',
        (asset_id,),
        fetch_one=True
    )
    return asset
