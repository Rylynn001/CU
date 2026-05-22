import logging

logger = logging.getLogger('comfy_api_proxy')

try:
    from . import routes  # 注册所有路由
    from .task_routes import auth_routes
    from .hooks import asset_hook
    from server import PromptServer

    # 注册认证路由
    auth_routes.add_auth_routes(PromptServer.instance.routes)

    # 安装资产保存 hook
    asset_hook.setup_asset_hook(PromptServer.instance)

    # 启动 Worker 线程
    if routes.REDIS_AVAILABLE:
        import threading
        from . import worker
        worker_thread = threading.Thread(target=worker.main, daemon=True, name='RedisWorker')
        worker_thread.start()
        logger.info('[comfy_api_proxy] Redis worker started in background')
    else:
        logger.warning('[comfy_api_proxy] Redis not available, worker not started')

    logger.info('[comfy_api_proxy] routes registered: /api-proxy/*, /auth/*')
except Exception as e:
    logger.error(f'[comfy_api_proxy] failed to register routes: {e}')

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
