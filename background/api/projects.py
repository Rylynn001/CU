"""项目管理相关路由"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from api.auth import get_current_user
from database import execute_query, get_db

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str


class ProjectRename(BaseModel):
    name: str


class CategoryCreate(BaseModel):
    project_id: int
    name: str


class CategoryRename(BaseModel):
    name: str


class AssetToCategory(BaseModel):
    asset_id: int
    resubmit_id: int | None = None


@router.get("/projects")
async def get_projects(current_user: dict = Depends(get_current_user)):
    """获取用户项目列表"""
    user_id = current_user['user_id']

    projects = execute_query(
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

    return {'projects': projects}


@router.get("/projects/{project_id}")
async def get_project_detail(
    project_id: int,
    current_user: dict = Depends(get_current_user)
):
    """获取项目详情"""
    user_id = current_user['user_id']

    # 检查权限
    member = execute_query(
        'SELECT role FROM project_members WHERE project_id = %s AND user_id = %s',
        (project_id, user_id),
        fetch_one=True
    )

    if not member:
        raise HTTPException(status_code=403, detail='非项目成员或项目不存在')

    # 获取项目信息
    project = execute_query(
        'SELECT id, name FROM projects WHERE id = %s AND del_flag = 0',
        (project_id,),
        fetch_one=True
    )

    # 获取分类
    categories = execute_query(
        '''SELECT pc.id, pc.name,
                  (SELECT COUNT(*) FROM category_assets ca
                   WHERE ca.category_id = pc.id) AS asset_count
           FROM project_category pc
           WHERE pc.project_id = %s AND pc.del_flag = 0
           ORDER BY pc.id''',
        (project_id,),
        fetch_all=True
    ) or []

    return {
        'id': project['id'],
        'name': project['name'],
        'role': member['role'],
        'categories': categories
    }


@router.get("/projects/{project_id}/categories")
async def get_project_categories(
    project_id: int,
    current_user: dict = Depends(get_current_user)
):
    """获取项目分类"""
    user_id = current_user['user_id']

    # 检查权限
    member = execute_query(
        'SELECT role FROM project_members WHERE project_id = %s AND user_id = %s',
        (project_id, user_id),
        fetch_one=True
    )

    if not member:
        raise HTTPException(status_code=403, detail='非项目成员')

    categories = execute_query(
        '''SELECT pc.id, pc.name,
                  (SELECT COUNT(*) FROM category_assets ca
                   WHERE ca.category_id = pc.id) AS asset_count
           FROM project_category pc
           WHERE pc.project_id = %s AND pc.del_flag = 0
           ORDER BY pc.id''',
        (project_id,),
        fetch_all=True
    ) or []

    return {'categories': categories}


@router.post("/projects")
async def create_project(
    req: ProjectCreate,
    current_user: dict = Depends(get_current_user)
):
    """创建项目"""
    user_id = current_user['user_id']

    if not req.name.strip():
        raise HTTPException(status_code=400, detail='name is required')

    # 创建项目
    project_id = execute_query(
        'INSERT INTO projects (name, del_flag) VALUES (%s, 0)',
        (req.name.strip(),)
    )

    # 添加创建者为 owner
    execute_query(
        'INSERT INTO project_members (project_id, user_id, role) VALUES (%s, %s, %s)',
        (project_id, user_id, 'owner')
    )

    # 创建默认分类
    default_categories = ['待提交', '待审核', '已通过', '未通过']
    category_ids = []
    for cat_name in default_categories:
        cat_id = execute_query(
            'INSERT INTO project_category (project_id, name, del_flag) VALUES (%s, %s, 0)',
            (project_id, cat_name)
        )
        category_ids.append({'id': cat_id, 'name': cat_name})

    return {
        'id': project_id,
        'name': req.name,
        'role': 'owner',
        'categories': category_ids
    }


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: int,
    current_user: dict = Depends(get_current_user)
):
    """删除项目"""
    user_id = current_user['user_id']

    # 检查权限
    member = execute_query(
        'SELECT role FROM project_members WHERE project_id = %s AND user_id = %s',
        (project_id, user_id),
        fetch_one=True
    )

    if not member or member['role'] != 'owner':
        raise HTTPException(status_code=403, detail='项目不存在或无权限')

    execute_query('UPDATE projects SET del_flag = 1 WHERE id = %s', (project_id,))
    return {'ok': True}


@router.put("/projects/{project_id}")
async def rename_project(
    project_id: int,
    req: ProjectRename,
    current_user: dict = Depends(get_current_user)
):
    """重命名项目"""
    user_id = current_user['user_id']

    if not req.name.strip():
        raise HTTPException(status_code=400, detail='name is required')

    # 检查权限
    member = execute_query(
        'SELECT role FROM project_members WHERE project_id = %s AND user_id = %s',
        (project_id, user_id),
        fetch_one=True
    )

    if not member or member['role'] not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail='项目不存在或无权限')

    execute_query(
        'UPDATE projects SET name = %s WHERE id = %s',
        (req.name.strip(), project_id)
    )

    return {'ok': True}


@router.post("/categories")
async def create_category(req: CategoryCreate):
    """创建分类"""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail='name is required')

    cat_id = execute_query(
        'INSERT INTO project_category (project_id, name, del_flag) VALUES (%s, %s, 0)',
        (req.project_id, req.name.strip())
    )

    return {'id': cat_id, 'name': req.name}


@router.delete("/categories/{category_id}")
async def delete_category(category_id: int):
    """删除分类"""
    execute_query('UPDATE project_category SET del_flag = 1 WHERE id = %s', (category_id,))
    return {'ok': True}


@router.put("/categories/{category_id}")
async def rename_category(category_id: int, req: CategoryRename):
    """重命名分类"""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail='name is required')

    execute_query(
        'UPDATE project_category SET name = %s WHERE id = %s',
        (req.name.strip(), category_id)
    )

    return {'ok': True}


@router.get("/categories/{category_id}/assets")
async def get_category_assets(category_id: int):
    """获取分类下的资产"""
    assets = execute_query(
        '''SELECT a.* FROM assets a
           INNER JOIN category_assets ca ON a.id = ca.assets_id
           WHERE ca.category_id = %s
           ORDER BY ca.created_at DESC''',
        (category_id,),
        fetch_all=True
    ) or []

    return {'assets': assets}


@router.post("/categories/{category_id}/assets")
async def add_asset_to_category(
    category_id: int,
    req: AssetToCategory,
    current_user: dict = Depends(get_current_user)
):
    """添加资产到分类"""
    user_id = current_user['user_id']

    # 检查用户是否是项目成员
    member = execute_query(
        '''SELECT pm.role FROM project_members pm
           INNER JOIN project_category c ON pm.project_id = c.project_id
           WHERE c.id = %s AND pm.user_id = %s''',
        (category_id, user_id),
        fetch_one=True
    )

    if not member:
        raise HTTPException(status_code=403, detail='非项目成员')

    # 添加资产
    execute_query(
        'INSERT INTO category_assets (category_id, assets_id, submitted_by, review_status, created_at) VALUES (%s, %s, %s, %s, NOW())',
        (category_id, req.asset_id, user_id, 'pending')
    )

    return {'ok': True, 'review_status': 'pending'}


@router.delete("/categories/{category_id}/assets/{asset_id}")
async def remove_asset_from_category(category_id: int, asset_id: int):
    """从分类移除资产"""
    execute_query(
        'DELETE FROM category_assets WHERE category_id = %s AND assets_id = %s',
        (category_id, asset_id)
    )

    return {'ok': True}


@router.get("/pending-assets")
async def list_pending_assets(
    page: int = 1,
    page_size: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """列出用户有权限审核的所有待审核素材（仅 owner/admin）"""
    user_id = current_user['user_id']
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size

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

    return {'assets': assets, 'total': total, 'page': page, 'page_size': page_size}


@router.get("/my-submissions")
async def list_my_submissions(
    page: int = 1,
    page_size: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """列出当前用户提交的所有素材及其审核状态"""
    user_id = current_user['user_id']
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size

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

    return {
        'submissions': submissions,
        'total': counts['cnt'],
        'rejected_total': counts['rejected_count'],
        'page': page,
        'page_size': page_size
    }


@router.get("/projects/{project_id}/members")
async def get_project_members(
    project_id: int,
    current_user: dict = Depends(get_current_user)
):
    """获取项目成员列表"""
    members = execute_query(
        '''SELECT pm.user_id, pm.role, pm.created_at,
                  u.user_name AS username
           FROM project_members pm
           LEFT JOIN sys_user u ON u.id = pm.user_id
           WHERE pm.project_id = %s
           ORDER BY pm.created_at''',
        (project_id,),
        fetch_all=True
    ) or []

    for m in members:
        if m.get('created_at'):
            m['created_at'] = m['created_at'].strftime('%Y-%m-%d %H:%M:%S')

    return {'members': members}


class AddMemberRequest(BaseModel):
    username: str
    role: str = 'member'


@router.post("/projects/{project_id}/members")
async def add_project_members(
    project_id: int,
    req: AddMemberRequest,
    current_user: dict = Depends(get_current_user)
):
    """添加项目成员"""
    # 根据用户名查找用户
    user = execute_query(
        'SELECT id, user_name FROM sys_user WHERE user_name = %s',
        (req.username.strip(),),
        fetch_one=True
    )
    if not user:
        raise HTTPException(status_code=404, detail='用户不存在')

    target_user_id = user['id']

    # 检查是否已存在
    existing = execute_query(
        'SELECT id FROM project_members WHERE project_id = %s AND user_id = %s',
        (project_id, target_user_id),
        fetch_one=True
    )
    if existing:
        raise HTTPException(status_code=400, detail='该用户已是项目成员')

    if req.role not in ('admin', 'member'):
        raise HTTPException(status_code=400, detail='role 只能是 admin 或 member')

    execute_query(
        'INSERT INTO project_members (project_id, user_id, role, created_at) VALUES (%s, %s, %s, NOW())',
        (project_id, target_user_id, req.role)
    )

    return {'ok': True, 'user_id': target_user_id, 'username': req.username, 'role': req.role}


@router.put("/projects/{project_id}/members/{member_user_id}")
async def update_project_members(
    project_id: int,
    member_user_id: int,
    role: str,
    current_user: dict = Depends(get_current_user)
):
    """更新项目成员角色"""
    execute_query(
        'UPDATE project_members SET role = %s WHERE project_id = %s AND user_id = %s',
        (role, project_id, member_user_id)
    )

    return {'success': True}


@router.delete("/projects/{project_id}/members/{member_user_id}")
async def remove_project_members(
    project_id: int,
    member_user_id: int,
    current_user: dict = Depends(get_current_user)
):
    """移除项目成员"""
    execute_query(
        'DELETE FROM project_members WHERE project_id = %s AND user_id = %s',
        (project_id, member_user_id)
    )

    return {'success': True}


@router.get("/projects/{project_id}/candidate-users")
async def get_candidate_users(
    project_id: int,
    page: int = 1,
    page_size: int = 50,
    keyword: str = '',
    current_user: dict = Depends(get_current_user)
):
    """获取可添加的候选用户（未加入该项目的用户）"""
    # 构建基础查询条件
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
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size

    users = execute_query(
        f'''SELECT u.id, u.user_name, u.real_name
           FROM sys_user u
           {base_condition}
           ORDER BY u.real_name
           LIMIT %s OFFSET %s''',
        tuple(params + [page_size, offset]),
        fetch_all=True
    ) or []

    return {'users': users, 'total': total, 'page': page, 'page_size': page_size}


class ReviewRequest(BaseModel):
    approve: bool
    comment: str | None = None


@router.post("/categories/{category_id}/assets/{asset_id}/review")
async def review_asset(
    category_id: int,
    asset_id: int,
    req: ReviewRequest,
    current_user: dict = Depends(get_current_user)
):
    """审核资产（approve/reject）"""
    user_id = current_user['user_id']

    # 检查权限和状态
    ca_row = execute_query(
        '''SELECT ca.id, ca.review_status, p.id AS project_id
           FROM category_assets ca
           JOIN categories c ON c.id = ca.category_id
           JOIN projects p ON p.id = c.project_id
           WHERE ca.category_id = %s AND ca.assets_id = %s''',
        (category_id, asset_id),
        fetch_one=True
    )
    if not ca_row:
        raise HTTPException(status_code=404, detail='资产不在该分类中')

    # 检查用户是否是该项目的 owner 或 admin
    role_row = execute_query(
        'SELECT role FROM project_members WHERE project_id = %s AND user_id = %s',
        (ca_row['project_id'], user_id),
        fetch_one=True
    )
    if not role_row or role_row['role'] not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail='无权限审核')

    if ca_row['review_status'] != 'pending':
        raise HTTPException(status_code=400, detail='该素材不在待审核状态')

    # 更新审核状态
    new_status = 'approved' if req.approve else 'rejected'
    action = 'approve' if req.approve else 'reject'

    execute_query(
        'UPDATE category_assets SET review_status = %s WHERE category_id = %s AND assets_id = %s',
        (new_status, category_id, asset_id)
    )

    # 记录审核历史
    execute_query(
        '''INSERT INTO category_asset_reviews (category_assets_id, reviewer_id, action, comment, created_at)
           VALUES (%s, %s, %s, %s, NOW())''',
        (ca_row['id'], user_id, action, req.comment)
    )

    return {'ok': True, 'new_status': new_status}


@router.get("/categories/{category_id}/assets/{asset_id}/reviews")
async def get_asset_reviews(
    category_id: int,
    asset_id: int,
    current_user: dict = Depends(get_current_user)
):
    """获取资产的审核时间线（含权限检查）"""
    user_id = current_user['user_id']

    # 检查权限：项目 owner/admin 或提交人本人
    info = execute_query(
        '''SELECT ca.id, pc.project_id, ca.submitted_by
           FROM project_category pc
           JOIN category_assets ca ON ca.category_id = pc.id
           WHERE pc.id = %s AND ca.assets_id = %s''',
        (category_id, asset_id),
        fetch_one=True
    )

    if not info:
        raise HTTPException(status_code=404, detail='资产不存在')

    # 检查权限
    role = execute_query(
        'SELECT role FROM project_members WHERE project_id = %s AND user_id = %s',
        (info['project_id'], user_id),
        fetch_one=True
    )

    # member 角色也能查看（旧版逻辑）
    if not role or (role['role'] not in ('owner', 'admin', 'member') and info['submitted_by'] != user_id):
        raise HTTPException(status_code=403, detail='无权限查看')

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

    for r in reviews:
        if r.get('created_at'):
            r['created_at'] = r['created_at'].strftime('%Y-%m-%d %H:%M:%S')

    return reviews
