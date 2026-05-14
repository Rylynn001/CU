import logging

logger = logging.getLogger('comfy_api_proxy')

try:
    from . import routes  # 注册所有路由
    from . import auth
    from . import asset_hook
    from server import PromptServer

    # 注册认证路由
    auth.add_auth_routes(PromptServer.instance.routes)

    # 安装资产保存 hook
    asset_hook.setup_asset_hook(PromptServer.instance)

    # 自动运行数据迁移（仅在首次加载时）
    try:
        from . import migrate_to_db
        migrate_to_db.run_migration()
    except Exception as e:
        logger.warning(f'[api-proxy] Migration skipped or failed: {e}')

    # 启动 Worker 线程（处理 Redis 队列任务）
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

# ComfyUI 要求 NODE_CLASS_MAPPINGS（即使没有自定义节点也要有）
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
