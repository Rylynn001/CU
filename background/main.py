"""FastAPI 主入口"""
import logging
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from core import setup_exception_handlers
from api import auth, assets, providers, history, projects, tasks, node_boards, dramas, generation, common
from api import agent, gecko, workflow  # 添加 workflow 路由

logger = logging.getLogger(__name__)


def start_workers():
    """启动 worker（协程版本）"""
    import asyncio
    from worker import main as worker_main

    logger.info('正在启动 worker...')

    def run_async_workers():
        """在独立线程中运行异步事件循环"""
        asyncio.run(worker_main())

    t = threading.Thread(
        target=run_async_workers,
        daemon=True,
        name='WorkerThread',
    )
    t.start()

    logger.info('worker 已启动')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 配置日志轮转（保留最近 3 次启动的日志）
    from utils.log_rotator import setup_rotating_logger, configure_logging
    log_file = setup_rotating_logger(log_dir="logs", max_files=3)
    configure_logging(log_file, level=logging.INFO)

    logger.info("FastAPI 应用启动")
    start_workers()

    # 启动 Gecko 定时任务
    from api.gecko import start_scheduler
    start_scheduler()

    yield
    logger.info("FastAPI 应用关闭")


app = FastAPI(
    title="CU Background API",
    description="ComfyUI API 代理服务 - FastAPI 重构版",
    version="2.0.0",
    lifespan=lifespan
)

# 注册全局异常处理器
setup_exception_handlers(app)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由（兼容旧版路径）
app.include_router(auth.router, prefix="/auth", tags=["认证"])
app.include_router(common.router, tags=["通用"])  # /view 等通用接口不加前缀
app.include_router(providers.router, prefix="/api-proxy", tags=["模型提供商"])
app.include_router(assets.router, prefix="/api-proxy", tags=["资产管理"])
app.include_router(history.router, prefix="/api-proxy", tags=["历史记录"])
app.include_router(projects.router, prefix="/api-proxy", tags=["项目管理"])
app.include_router(tasks.router, prefix="/api-proxy", tags=["任务管理"])
app.include_router(node_boards.router, prefix="/api-proxy", tags=["工作区管理"])
app.include_router(dramas.router, prefix="/api-proxy", tags=["短剧管理"])
app.include_router(generation.router, prefix="/api-proxy", tags=["图片视频生成"])
app.include_router(agent.router, prefix="/api-proxy", tags=["AI Agent"])
app.include_router(gecko.router, prefix="/api-proxy", tags=["Gecko集成"])
app.include_router(workflow.router, prefix="/api-proxy", tags=["工作流"])


@app.get("/")
async def root():
    return {
        "service": "CU Background API",
        "version": "2.0.0",
        "status": "running"
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )


