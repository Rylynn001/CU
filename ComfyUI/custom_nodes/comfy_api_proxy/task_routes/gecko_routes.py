"""Gecko 相关路由：初始化 / 获取当前账号信息"""
import logging
from aiohttp import web
from server import PromptServer

logger = logging.getLogger('comfy_api_proxy')
routes = PromptServer.instance.routes


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
    from ..utils.http_client import post
    from requests.exceptions import RequestException

    # 获取并打印客户端 IP
    client_ip = get_client_ip(request)
    logger.info(f'[gecko] 客户端 IP: {client_ip}')
    print(f'[Gecko Init] 客户端 IP: {client_ip}')

    try:
        result = post(
            'https://192.168.0.25/api/python-v2/get_current_account_data',
            json={'ip_address': client_ip}
        )
        success = result.get('success', False)
        data = result.get('data') or {}
        name = data.get('acount.name')
        account_id = data.get('acount.id')
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
