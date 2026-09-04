"""Gecko 相关路由：初始化 / 获取当前账号信息"""
import asyncio
import logging
from aiohttp import web
from server import PromptServer
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger('comfy_api_proxy')
routes = PromptServer.instance.routes

# Gecko 专用 HTTP 客户端：更短的超时和重试，避免阻塞线程池
_gecko_client = None

def get_gecko_client():
    """获取 Gecko 专用的 HTTP 客户端（5秒超时，仅重试1次）"""
    global _gecko_client
    if _gecko_client is None:
        from ..utils.http_client import HttpClient
        _gecko_client = HttpClient(timeout=5, retry_delay=0.5)
        _gecko_client.max_retries = 1
    return _gecko_client


def get_client_ip(request: web.Request) -> str:
    """获取客户端真实 IPv4 地址"""
    # 优先从代理头获取
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # X-Forwarded-For 可能包含多个 IP，取第一个
        return forwarded_for.split(',')[0].strip()

    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()

    # 从 peername 获取
    peername = request.transport.get_extra_info('peername')
    if peername:
        return peername[0]

    return 'unknown'


@routes.post('/api-proxy/gecko/init')
async def gecko_init(request: web.Request):
    from requests.exceptions import RequestException

    # 获取并打印客户端 IP
    client_ip = get_client_ip(request)
    logger.info(f'[gecko] 客户端 IP: {client_ip}')
    print(f'[Gecko Init] 客户端 IP: {client_ip}')

    try:
        # 使用 Gecko 专用客户端，在线程池执行同步请求
        gecko_client = get_gecko_client()
        result = await asyncio.to_thread(
            gecko_client.post,
            'https://192.168.0.25/api/python-v2/get_current_account_data',
            json={'ip_address': client_ip}
        )
        success = result.get('success', False)
        data = result.get('data') or {}
        name = data.get('account.name')
        account_id = data.get('account.id')
        department = data.get('account.department')

        logger.info(f'[gecko] 初始化响应: success={success}, name={name}, id={account_id}, department={department}')
        print(f'[Gecko Init] 响应: success={success}, name={name}, id={account_id}, department={department}')

        if not success:
            return web.json_response({
                'success': False,
                'message': '请先登录Gecko'
            })

        return web.json_response({
            'success': True,
            'name': name,
            'id': account_id,
            'department': department,
            'ip': client_ip,
        })
    except RequestException as e:
        logger.error(f'[gecko] 初始化失败: {e}', exc_info=True)
        print(f'[Gecko Init] 初始化失败: {e}')
        return web.json_response({
            'success': False,
            'message': f'请先登录Gecko（{e}）'
        }, status=200)
    except Exception as e:
        logger.error(f'[gecko] 初始化异常: {e}', exc_info=True)
        print(f'[Gecko Init] 初始化异常: {e}')
        raise web.HTTPInternalServerError(reason=str(e))


@routes.post('/api-proxy/gecko/tasks')
async def gecko_tasks(request: web.Request):
    from requests.exceptions import RequestException

    client_ip = get_client_ip(request)
    body = await request.json() if request.can_read_body else {}
    page = body.get('page', 1)

    try:
        # 使用 Gecko 专用客户端，在线程池执行同步请求
        gecko_client = get_gecko_client()
        result = await asyncio.to_thread(
            gecko_client.post,
            'https://192.168.0.25/api/python-v2/get_my_active_tasks',
            json={
                'page': page,
                'page_size': 50,
                'ip_address': client_ip,
                'task_type':'shot',
                'filter_list': [],
                'sort': '-updated_at',
            }
        )
        success = result.get('success', False)
        data = result.get('data') or {}
        total_count= data.get('total_count', 0)
        data_list: list = data.get('data_list',[])
        result_list: list = []
        for item in data_list:
            r1 = {
                'task_id': item.get('task.id'),
                'project_name': item.get('task.project_name'),
                'task_artist': item.get('task.artist'),
                'task_name': item.get('task.task_name'),
                'task_type': item.get('task.task_type'),
                'eps_name': item.get('shot.eps_name'),
                'shot': item.get('shot.shot')
            }
            result_list.append(r1)

        if not success:
            return web.json_response({
                'success': False,
                'message': result.get('message') or '获取任务失败'
            })

        return web.json_response({
            'success': True,
            'total_count': total_count,
            'data_list': result_list,
        })
    except RequestException as e:
        logger.error(f'[gecko] 获取任务失败: {e}', exc_info=True)
        return web.json_response({
            'success': False,
            'message': f'获取任务失败（{e}）'
        }, status=200)
    except Exception as e:
        logger.error(f'[gecko] 获取任务异常: {e}', exc_info=True)
        raise web.HTTPInternalServerError(reason=str(e))


@routes.post('/api-proxy/gecko/upload-media')
async def gecko_upload_media(request: web.Request):
    """
    上传文件到 Gecko 任务目录

    接收前端的 multipart/form-data 请求，包含：
    - project_name: 项目名称
    - eps_name: 集数名称
    - shot: 镜头名称
    - user_name: 用户名
    - files: 多个文件（字段名都是 'files'）

    转发给 Gecko API: /api/python-v2/upload_media
    - 普通字段映射: eps_name -> sequence_name, shot -> shot_name
    - 文件字段保持 'files' 作为字段名，支持多文件上传
    """
    from requests.exceptions import RequestException
    import aiohttp

    try:
        logger.info('[gecko_upload_media] ========== 开始处理上传请求 ==========')

        # 步骤1: 读取 multipart/form-data
        reader = await request.multipart()

        # 步骤2: 收集表单字段和文件
        form_data = {}
        files_data = []

        async for field in reader:
            if field.filename:
                # 文件字段：收集文件内容和元信息
                file_content = await field.read()
                file_info = {
                    'name': field.name,  # 字段名（应该是 'files'）
                    'filename': field.filename,  # 文件名
                    'content': file_content,
                    'content_type': field.headers.get('Content-Type', 'application/octet-stream'),
                    'size': len(file_content)
                }
                files_data.append(file_info)
                logger.info(f'[gecko_upload_media] 收到文件: name={field.name}, filename={field.filename}, size={len(file_content)} bytes, type={file_info["content_type"]}')
            else:
                # 普通字段：收集表单数据
                field_value = (await field.read()).decode('utf-8')
                form_data[field.name] = field_value
                logger.info(f'[gecko_upload_media] 收到字段: {field.name}={field_value}')

        # 步骤3: 提取必要参数
        project_name = form_data.get('project_name')
        eps_name = form_data.get('eps_name')
        shot = form_data.get('shot')
        user_name = form_data.get('user_name')

        logger.info(f'[gecko_upload_media] 解析参数: project_name={project_name}, eps_name={eps_name}, shot={shot}, user_name={user_name}, 文件数量={len(files_data)}')

        # 检查必要参数
        if not all([project_name, eps_name, shot, user_name]):
            logger.error(f'[gecko_upload_media] 缺少必要参数')
            return web.json_response({
                'success': False,
                'message': '缺少必要参数'
            })

        if not files_data:
            logger.error(f'[gecko_upload_media] 没有文件')
            return web.json_response({
                'success': False,
                'message': '没有文件'
            })

        # 步骤4: 构建发送给 Gecko 的 form-data
        logger.info('[gecko_upload_media] 构建发送给 Gecko 的 form-data...')
        form = aiohttp.FormData()

        # 添加普通字段（注意：eps_name 映射为 sequence_name, shot 映射为 shot_name）
        form.add_field('project_name', project_name)
        form.add_field('sequence_name', eps_name)  # Gecko API 要求的字段名
        form.add_field('shot_name', shot)  # Gecko API 要求的字段名
        form.add_field('user_name', user_name)
        logger.info(f'[gecko_upload_media] 添加字段: project_name={project_name}, sequence_name={eps_name}, shot_name={shot}, user_name={user_name}')

        # 添加文件字段（每个文件都用 'files' 作为字段名，符合多文件上传规范）
        for idx, file_item in enumerate(files_data):
            form.add_field(
                'files',  # 字段名固定为 'files'
                file_item['content'],
                filename=file_item['filename'],
                content_type=file_item['content_type']
            )
            logger.info(f'[gecko_upload_media] 添加文件[{idx}]: files={file_item["filename"]}, size={file_item["size"]} bytes, type={file_item["content_type"]}')

        # 步骤5: 发送请求到 Gecko API
        gecko_url = 'https://192.168.0.25/api/python-v2/upload_media'
        logger.info(f'[gecko_upload_media] 发送请求到 Gecko: {gecko_url}')

        async with aiohttp.ClientSession() as session:
            async with session.post(
                gecko_url,
                data=form,
                ssl=False,
                timeout=aiohttp.ClientTimeout(total=60)  # 设置60秒超时
            ) as resp:
                result = await resp.json()

        logger.info(f'[gecko_upload_media] Gecko 响应: {result}')

        # 步骤6: 处理响应
        success = result.get('success', False)
        if not success:
            error_msg = result.get('message') or '上传失败'
            logger.error(f'[gecko_upload_media] 上传失败: {error_msg}')
            return web.json_response({
                'success': False,
                'message': error_msg
            })

        logger.info('[gecko_upload_media] ========== 上传成功 ==========')
        return web.json_response({
            'success': True,
            'message': '上传成功',
            'data': result.get('data')
        })

    except RequestException as e:
        logger.error(f'[gecko_upload_media] 请求异常: {e}', exc_info=True)
        return web.json_response({
            'success': False,
            'message': f'上传失败（{e}）'
        }, status=200)
    except Exception as e:
        logger.error(f'[gecko_upload_media] 未知异常: {e}', exc_info=True)
        raise web.HTTPInternalServerError(reason=str(e))


# ========== 定时任务：每天凌晨1点自动登录 ==========
@routes.post('/api-proxy/gecko/daily-login')
async def daily_login():
    """每天凌晨1点执行登录"""
    import aiohttp

    try:
        logger.info('[gecko定时任务] 开始执行每日登录')
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://192.168.0.25/api/login',
                json={
                    'username': 'ai_node_creation_platform',
                    'password': '9yz4HpTyuBLwroW'
                },
                ssl=False,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                result = await resp.json()
                logger.info(f'[gecko定时任务] 登录响应: {result}')
    except Exception as e:
        logger.error(f'[gecko定时任务] 执行失败: {e}', exc_info=True)


# 启动定时任务调度器
scheduler = AsyncIOScheduler()
scheduler.add_job(daily_login, 'cron', hour=1, minute=0, id='gecko_daily_login')
scheduler.start()
logger.info('[gecko] 定时任务已启动：每天凌晨1点自动登录')


