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


@routes.post('/api-proxy/gecko/task-directories')
async def gecko_task_directories(request: web.Request):
    from requests.exceptions import RequestException

    body = await request.json() if request.can_read_body else {}
    project_name = body.get('project_name')
    task_id = body.get('task_id')
    task_type = body.get('task_type')

    logger.info(f'[gecko] 请求任务目录: project={project_name}, task_id={task_id}, task_type={task_type}')
    print(f'[Gecko Task Directories] 请求参数: project={project_name}, task_id={task_id}, task_type={task_type}')

    if task_type == 'assets':
        url = 'https://192.168.0.25/api/python-v2/get_project_asset_task_directories'
    else:
        url = 'https://192.168.0.25/api/python-v2/get_project_shot_task_directories'

    logger.info(f'[gecko] 目标URL: {url}')
    print(f'[Gecko Task Directories] 目标URL: {url}')

    try:
        # 使用 Gecko 专用客户端，在线程池执行同步请求
        gecko_client = get_gecko_client()
        result = await asyncio.to_thread(
            gecko_client.post,
            url,
            json={'project': project_name, 'task_id': task_id}
        )

        logger.info(f'[gecko] API响应: {result}')
        print(f'[Gecko Task Directories] API响应: {result}')

        success = result.get('success', False)
        data = result.get('data') or []

        logger.info(f'[gecko] 解析结果: success={success}, data条数={len(data)}')
        print(f'[Gecko Task Directories] 解析: success={success}, data={data}')

        dir1 = ''
        for item in data:
            title = item.get("title")
            logger.info(f'[gecko] 遍历目录项: title={title}, dir={item.get("dir")}')
            print(f'[Gecko Task Directories] 目录项: title={title}, dir={item.get("dir")}')
            if title == 'Work':
                dir1 = item.get('dir')
                logger.info(f'[gecko] 找到Work目录: {dir1}')
                print(f'[Gecko Task Directories] 找到Work目录: {dir1}')
                break

        if not success:
            logger.warning(f'[gecko] API返回失败: {result.get("message")}')
            print(f'[Gecko Task Directories] API失败: {result.get("message")}')
            return web.json_response({
                'success': False,
                'message': result.get('message') or '获取任务目录失败'
            })

        if not dir1:
            logger.warning(f'[gecko] 未找到Work目录，返回的data: {data}')
            print(f'[Gecko Task Directories] 警告: 未找到Work目录')

        logger.info(f'[gecko] 最终返回目录: {dir1}')
        print(f'[Gecko Task Directories] 成功返回: {dir1}')

        return web.json_response({
            'success': True,
            'message': dir1,
        })
    except RequestException as e:
        logger.error(f'[gecko] 获取任务目录失败: {e}', exc_info=True)
        print(f'[Gecko Task Directories] 请求失败: {e}')
        return web.json_response({
            'success': False,
            'message': f'获取任务目录失败（{e}）'
        }, status=200)
    except Exception as e:
        logger.error(f'[gecko] 获取任务目录异常: {e}', exc_info=True)
        print(f'[Gecko Task Directories] 异常: {e}')
        raise web.HTTPInternalServerError(reason=str(e))
