"""Gecko 相关路由：初始化 / 获取当前账号信息"""
import asyncio
import logging
from aiohttp import web
from server import PromptServer

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
    """上传文件到 Gecko 任务目录"""
    from requests.exceptions import RequestException
    import aiohttp

    try:
        # 读取 multipart/form-data
        reader = await request.multipart()

        # 收集表单字段和文件
        form_data = {}
        files_data = []

        async for field in reader:
            if field.filename:
                # 文件字段
                file_content = await field.read()
                files_data.append({
                    'name': field.name,
                    'filename': field.filename,
                    'content': file_content,
                    'content_type': field.headers.get('Content-Type', 'application/octet-stream')
                })
            else:
                # 普通字段
                form_data[field.name] = (await field.read()).decode('utf-8')

        project_name = form_data.get('project_name')
        eps_name = form_data.get('eps_name')
        shot = form_data.get('shot')
        user_name = form_data.get('user_name')
        version_name = form_data.get('version_name')

        logger.info(f'[gecko] 上传文件: project={project_name}, eps={eps_name}, shot={shot}, user={user_name}, version={version_name}, files={len(files_data)}')

        # 构建 form-data 发送给 Gecko
        form = aiohttp.FormData()
        form.add_field('project_name', project_name)
        form.add_field('sequence_name', eps_name)
        form.add_field('shot_name', shot)
        form.add_field('user_name', user_name)
        form.add_field('version_name', version_name)

        for file_item in files_data:
            form.add_field(
                'files',
                file_item['content'],
                filename=file_item['filename'],
                content_type=file_item['content_type']
            )

        # 发送请求到 Gecko
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://192.168.0.25/api/python-v2/upload_media',
                data=form,
                ssl=False
            ) as resp:
                result = await resp.json()

        logger.info(f'[gecko] 上传响应: {result}')

        success = result.get('success', False)
        if not success:
            return web.json_response({
                'success': False,
                'message': result.get('message') or '上传失败'
            })

        return web.json_response({
            'success': True,
            'message': '上传成功',
            'data': result.get('data')
        })

    except RequestException as e:
        logger.error(f'[gecko] 上传文件失败: {e}', exc_info=True)
        return web.json_response({
            'success': False,
            'message': f'上传失败（{e}）'
        }, status=200)
    except Exception as e:
        logger.error(f'[gecko] 上传文件异常: {e}', exc_info=True)
        raise web.HTTPInternalServerError(reason=str(e))
