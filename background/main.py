"""FastAPI 主入口"""
import logging
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from core import setup_exception_handlers
from api import auth, assets, providers, history, projects, tasks, node_boards, dramas, generation, common
from api import agent, gecko  # 暂时注释,测试循环导入问题

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def start_workers():
    """启动 worker 线程"""
    from worker import worker_loop, _get_redis

    redis_client = _get_redis()
    num_workers = settings.WORKER_COUNT
    logger.info(f'正在启动 {num_workers} 个 worker 线程...')

    for i in range(num_workers):
        t = threading.Thread(
            target=worker_loop,
            args=(i + 1, redis_client),
            daemon=True,
            name=f'Worker-{i+1}',
        )
        t.start()

    logger.info(f'{num_workers} 个 worker 已启动')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("FastAPI 应用启动")
    start_workers()
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
        reload=True
    )


