"""项目管理相关路由"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from api.auth import get_current_user
from repositories import project_repo

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

    projects = project_repo.get_user_projects(user_id)

    return {'projects': projects}


@router.get("/projects/{project_id}")
async def get_project_detail(
    project_id: int,
    current_user: dict = Depends(get_current_user)
):
    """获取项目详情"""
    user_id = current_user['user_id']

    # 检查权限
    member = project_repo.get_project_member(project_id, user_id)

    if not member:
        raise HTTPException(status_code=403, detail='非项目成员或项目不存在')

    # 获取项目信息
    project = project_repo.get_project_by_id(project_id)

    # 获取分类
    categories = project_repo.get_project_categories(project_id)

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
    member = project_repo.get_project_member(project_id, user_id)

    if not member:
        raise HTTPException(status_code=403, detail='非项目成员')

    categories = project_repo.get_project_categories(project_id)

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
    project_id = project_repo.create_project(req.name.strip(), user_id)

    # 创建默认分类
    default_categories = ['待提交', '待审核', '已通过', '未通过']
    category_ids = []
    for cat_name in default_categories:
        cat_id = project_repo.create_category(project_id, cat_name)
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
    member = project_repo.get_project_member(project_id, user_id)

    if not member or member['role'] != 'owner':
        raise HTTPException(status_code=403, detail='项目不存在或无权限')

    project_repo.delete_project(project_id)
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
    member = project_repo.get_project_member(project_id, user_id)

    if not member or member['role'] not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail='项目不存在或无权限')

    project_repo.update_project_name(project_id, req.name.strip())

    return {'ok': True}


@router.post("/categories")
async def create_category(req: CategoryCreate):
    """创建分类"""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail='name is required')

    cat_id = project_repo.create_category(req.project_id, req.name.strip())

    return {'id': cat_id, 'name': req.name}


@router.delete("/categories/{category_id}")
async def delete_category(category_id: int):
    """删除分类"""
    project_repo.delete_category(category_id)
    return {'ok': True}


@router.put("/categories/{category_id}")
async def rename_category(category_id: int, req: CategoryRename):
    """重命名分类"""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail='name is required')

    project_repo.update_category_name(category_id, req.name.strip())

    return {'ok': True}


@router.get("/categories/{category_id}/assets")
async def get_category_assets(category_id: int):
    """获取分类下的资产"""
    assets = project_repo.get_category_assets(category_id)

    return {'assets': assets}


@router.post("/categories/{category_id}/assets")
async def add_asset_to_category(
    category_id: int,
    req: AssetToCategory,
    current_user: dict = Depends(get_current_user)
):
    """添加资产到分类"""
    user_id = current_user['user_id']
    resubmit_id = req.resubmit_id

    # 检查用户是否是项目成员
    member = project_repo.get_member_role_in_category_project(category_id, user_id)

    if not member:
        raise HTTPException(status_code=403, detail='非项目成员')

    # 添加资产(支持续接被驳回的提交记录)
    if resubmit_id:
        # 续接逻辑:更新现有记录
        review_status = project_repo.resubmit_asset_to_category(
            category_id, req.asset_id, user_id, resubmit_id
        )
    else:
        # 全新提交
        review_status = project_repo.add_asset_to_category(
            category_id, req.asset_id, user_id
        )

    if review_status is None:
        raise HTTPException(status_code=403, detail='非项目成员或无权续接该提交记录')

    return {'ok': True, 'review_status': review_status}


@router.delete("/categories/{category_id}/assets/{asset_id}")
async def remove_asset_from_category(category_id: int, asset_id: int):
    """从分类移除资产"""
    project_repo.remove_asset_from_category(category_id, asset_id)

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

    assets, total = project_repo.get_user_pending_assets(user_id, page_size, offset)

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

    submissions, total, rejected_total = project_repo.get_user_submissions(user_id, page_size, offset)

    return {
        'submissions': submissions,
        'total': total,
        'rejected_total': rejected_total,
        'page': page,
        'page_size': page_size
    }


@router.get("/projects/{project_id}/members")
async def get_project_members(
    project_id: int,
    current_user: dict = Depends(get_current_user)
):
    """获取项目成员列表"""
    members = project_repo.get_project_members(project_id)

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
    user = project_repo.get_user_by_username(req.username.strip())
    if not user:
        raise HTTPException(status_code=404, detail='用户不存在')

    target_user_id = user['id']

    # 检查是否已存在
    if project_repo.check_project_member_exists(project_id, target_user_id):
        raise HTTPException(status_code=400, detail='该用户已是项目成员')

    if req.role not in ('admin', 'member'):
        raise HTTPException(status_code=400, detail='role 只能是 admin 或 member')

    project_repo.add_project_member(project_id, target_user_id, req.role)

    return {'ok': True, 'user_id': target_user_id, 'username': req.username, 'role': req.role}


@router.put("/projects/{project_id}/members/{member_user_id}")
async def update_project_members(
    project_id: int,
    member_user_id: int,
    role: str,
    current_user: dict = Depends(get_current_user)
):
    """更新项目成员角色"""
    project_repo.update_project_member_role(project_id, member_user_id, role)

    return {'success': True}


@router.delete("/projects/{project_id}/members/{member_user_id}")
async def remove_project_members(
    project_id: int,
    member_user_id: int,
    current_user: dict = Depends(get_current_user)
):
    """移除项目成员"""
    project_repo.remove_project_member(project_id, member_user_id)

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
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size

    users, total = project_repo.get_candidate_users(project_id, keyword, page_size, offset)

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

    # 调用 repo 层的审核逻辑（包含所有权限检查和状态更新）
    ok = project_repo.review_asset(category_id, asset_id, user_id, req.approve, req.comment)

    if not ok:
        raise HTTPException(status_code=403, detail='无权限审核或该素材不在待审核状态')

    return {'ok': True}


@router.get("/categories/{category_id}/assets/{asset_id}/reviews")
async def get_asset_reviews(
    category_id: int,
    asset_id: int,
    current_user: dict = Depends(get_current_user)
):
    """获取资产的审核时间线（含权限检查）"""
    user_id = current_user['user_id']

    # 调用 repo 层,包含完整的权限校验
    result = project_repo.get_asset_review_timeline(category_id, asset_id, user_id)

    if result is None:
        raise HTTPException(status_code=403, detail='无权限查看')

    # 格式化时间
    for r in result:
        if r.get('created_at'):
            r['created_at'] = r['created_at'].strftime('%Y-%m-%d %H:%M:%S')

    return result
