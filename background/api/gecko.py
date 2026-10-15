"""Gecko 集成相关路由 - 内部系统对接"""
import logging
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional
import httpx

router = APIRouter()
logger = logging.getLogger(__name__)

# Gecko API 基础配置
GECKO_BASE_URL = 'https://192.168.0.25'
GECKO_TIMEOUT = 60.0


def get_client_ip(request: Request) -> str:
    """获取客户端真实 IPv4 地址"""
    # 优先从代理头获取
    forwarded_for = request.headers.get('x-forwarded-for')
    if forwarded_for:
        # X-Forwarded-For 可能包含多个 IP，取第一个
        return forwarded_for.split(',')[0].strip()

    real_ip = request.headers.get('x-real-ip')
    if real_ip:
        return real_ip.strip()

    # 从客户端地址获取
    if request.client:
        return request.client.host

    return 'unknown'


class GeckoTasksRequest(BaseModel):
    page: int = 1


@router.post("/gecko/init")
async def gecko_init(request: Request):
    """
    Gecko 账号初始化 - 获取当前账号信息

    返回:
        {
            "success": true,
            "name": "用户名",
            "id": "账号ID",
            "department": "部门",
            "ip": "客户端IP"
        }
    """
    # 获取客户端 IP
    client_ip = get_client_ip(request)
    logger.info(f'[gecko-init] 客户端 IP: {client_ip}')

    try:
        async with httpx.AsyncClient(verify=False, timeout=GECKO_TIMEOUT) as client:
            resp = await client.post(
                f'{GECKO_BASE_URL}/api/python-v2/get_current_account_data',
                json={'ip_address': client_ip}
            )
            resp.raise_for_status()
            result = resp.json()

        success = result.get('success', False)
        data = result.get('data') or {}
        name = data.get('account.name')
        account_id = data.get('account.id')
        department = data.get('account.department')

        logger.info(f'[gecko-init] 响应: success={success}, name={name}, id={account_id}, department={department}')

        if not success:
            return {
                'success': False,
                'message': '请先登录 Gecko'
            }

        return {
            'success': True,
            'name': name,
            'id': account_id,
            'department': department,
            'ip': client_ip
        }

    except httpx.RequestError as e:
        logger.error(f'[gecko-init] 请求失败: {e}')
        return {
            'success': False,
            'message': f'请先登录 Gecko（{e}）'
        }
    except Exception as e:
        logger.error(f'[gecko-init] 异常: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gecko/tasks")
async def gecko_tasks(request: Request, req: GeckoTasksRequest):
    """
    获取 Gecko 任务列表

    请求体:
        { "page": 1 }

    返回:
        {
            "success": true,
            "total_count": 总数,
            "data_list": [
                {
                    "task_id": "任务ID",
                    "project_name": "项目名称",
                    "task_artist": "负责人",
                    "task_name": "任务名称",
                    "task_type": "任务类型",
                    "eps_name": "集数名称",
                    "shot": "镜头"
                }
            ]
        }
    """
    client_ip = get_client_ip(request)
    logger.info(f'[gecko-tasks] 客户端 IP: {client_ip}, page: {req.page}')

    try:
        async with httpx.AsyncClient(verify=False, timeout=GECKO_TIMEOUT) as client:
            resp = await client.post(
                f'{GECKO_BASE_URL}/api/python-v2/get_my_active_tasks',
                json={
                    'page': req.page,
                    'page_size': 50,
                    'ip_address': client_ip,
                    'task_type': 'shot',
                    'filter_list': [],
                    'sort': '-updated_at'
                }
            )
            resp.raise_for_status()
            result = resp.json()

        success = result.get('success', False)
        data = result.get('data') or {}
        total_count = data.get('total_count', 0)
        data_list = data.get('data_list', [])

        # 格式化任务列表
        result_list = []
        for item in data_list:
            result_list.append({
                'task_id': item.get('task.id'),
                'project_name': item.get('task.project_name'),
                'task_artist': item.get('task.artist'),
                'task_name': item.get('task.task_name'),
                'task_type': item.get('task.task_type'),
                'eps_name': item.get('shot.eps_name'),
                'shot': item.get('shot.shot')
            })

        if not success:
            return {
                'success': False,
                'message': result.get('message') or '获取任务失败'
            }

        logger.info(f'[gecko-tasks] 成功获取 {len(result_list)} 个任务')
        return {
            'success': True,
            'total_count': total_count,
            'data_list': result_list
        }

    except httpx.RequestError as e:
        logger.error(f'[gecko-tasks] 请求失败: {e}')
        return {
            'success': False,
            'message': f'获取任务失败（{e}）'
        }
    except Exception as e:
        logger.error(f'[gecko-tasks] 异常: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class TaskDirectoriesRequest(BaseModel):
    project_name: str
    task_id: str
    task_type: str


@router.post("/gecko/task-directories")
async def gecko_task_directories(req: TaskDirectoriesRequest):
    """
    获取任务目录结构

    请求体:
        {
            "project_name": "项目名称",
            "task_id": "任务ID",
            "task_type": "任务类型"
        }

    返回:
        {
            "success": true,
            "message": "目录信息"
        }
    """
    logger.info(f'[gecko-task-directories] project_name={req.project_name}, task_id={req.task_id}, task_type={req.task_type}')

    try:
        # 注意：这个接口可能需要根据实际 Gecko API 调整
        # 目前假设有一个获取任务目录的接口
        async with httpx.AsyncClient(verify=False, timeout=GECKO_TIMEOUT) as client:
            resp = await client.post(
                f'{GECKO_BASE_URL}/api/python-v2/get_task_directories',
                json={
                    'project_name': req.project_name,
                    'task_id': req.task_id,
                    'task_type': req.task_type
                }
            )
            resp.raise_for_status()
            result = resp.json()

        logger.info(f'[gecko-task-directories] 响应: {result}')
        return result

    except httpx.RequestError as e:
        logger.error(f'[gecko-task-directories] 请求失败: {e}')
        return {
            'success': False,
            'message': f'获取目录失败（{e}）'
        }
    except Exception as e:
        logger.error(f'[gecko-task-directories] 异常: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gecko/upload-media")
async def gecko_upload_media(
    request: Request,
    project_name: str = Form(...),
    eps_name: str = Form(...),
    shot: str = Form(...),
    user_name: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """
    上传媒体文件到 Gecko 任务目录

    表单参数:
        - project_name: 项目名称
        - eps_name: 集数名称
        - shot: 镜头名称
        - user_name: 用户名
        - files: 文件列表（支持多文件上传）

    返回:
        {
            "success": true,
            "message": "上传成功",
            "data": {...}
        }
    """
    logger.info(f'[gecko-upload-media] 开始处理上传: project_name={project_name}, eps_name={eps_name}, shot={shot}, user_name={user_name}, 文件数量={len(files)}')

    # 检查必要参数
    if not all([project_name, eps_name, shot, user_name]):
        raise HTTPException(status_code=400, detail='缺少必要参数')

    if not files:
        raise HTTPException(status_code=400, detail='没有文件')

    try:
        # 构建 multipart/form-data
        form_data = httpx.FormData()

        # 添加普通字段（注意：eps_name 映射为 sequence_name, shot 映射为 shot_name）
        form_data.add_field('project_name', project_name)
        form_data.add_field('sequence_name', eps_name)  # Gecko API 要求的字段名
        form_data.add_field('shot_name', shot)  # Gecko API 要求的字段名
        form_data.add_field('user_name', user_name)

        logger.info(f'[gecko-upload-media] 表单字段: project_name={project_name}, sequence_name={eps_name}, shot_name={shot}, user_name={user_name}')

        # 添加文件字段（每个文件都用 'files' 作为字段名，符合多文件上传规范）
        for idx, file in enumerate(files):
            file_content = await file.read()
            content_type = file.content_type or 'application/octet-stream'

            form_data.add_field(
                'files',  # 字段名固定为 'files'
                file_content,
                filename=file.filename,
                content_type=content_type
            )
            logger.info(f'[gecko-upload-media] 添加文件[{idx}]: files={file.filename}, size={len(file_content)} bytes, type={content_type}')

        # 发送请求到 Gecko API
        gecko_url = f'{GECKO_BASE_URL}/api/python-v2/upload_media'
        logger.info(f'[gecko-upload-media] 发送请求到: {gecko_url}')

        async with httpx.AsyncClient(verify=False, timeout=GECKO_TIMEOUT) as client:
            resp = await client.post(gecko_url, data=form_data)
            resp.raise_for_status()
            result = resp.json()

        logger.info(f'[gecko-upload-media] Gecko 响应: {result}')

        # 处理响应
        success = result.get('success', False)
        if not success:
            error_msg = result.get('message') or '上传失败'
            logger.error(f'[gecko-upload-media] 上传失败: {error_msg}')
            return {
                'success': False,
                'message': error_msg
            }

        logger.info('[gecko-upload-media] 上传成功')
        return {
            'success': True,
            'message': '上传成功',
            'data': result.get('data')
        }

    except httpx.RequestError as e:
        logger.error(f'[gecko-upload-media] 请求失败: {e}')
        return {
            'success': False,
            'message': f'上传失败（{e}）'
        }
    except Exception as e:
        logger.error(f'[gecko-upload-media] 异常: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
