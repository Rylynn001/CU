"""日志轮转工具"""
import os
import logging
from pathlib import Path
from datetime import datetime


def setup_rotating_logger(log_dir: str = "logs", max_files: int = 3) -> str:
    """
    设置日志轮转，保留最近 N 次启动的日志文件

    Args:
        log_dir: 日志目录路径（相对于 background/）
        max_files: 最多保留的日志文件数量

    Returns:
        当前日志文件的完整路径
    """
    # 获取 background 目录的绝对路径
    base_dir = Path(__file__).parent.parent
    log_path = base_dir / log_dir

    # 确保日志目录存在
    log_path.mkdir(exist_ok=True)

    # 获取所有现有日志文件，按修改时间排序
    log_files = sorted(
        log_path.glob("app_*.log"),
        key=lambda f: f.stat().st_mtime
    )

    # 如果已有日志文件数量 >= max_files，删除最旧的
    if len(log_files) >= max_files:
        files_to_delete = log_files[:len(log_files) - max_files + 1]
        for old_file in files_to_delete:
            try:
                # 先记录到控制台（此时文件日志还未配置）
                print(f"[日志轮转] 删除旧日志: {old_file.name}")
                old_file.unlink()
            except Exception as e:
                print(f"[日志轮转] 删除旧日志失败 {old_file.name}: {e}")

    # 创建新的日志文件（时间戳命名）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_log_file = log_path / f"app_{timestamp}.log"

    print(f"[日志轮转] 创建新日志: {current_log_file.name}")

    return str(current_log_file)


def configure_logging(log_file: str, level: int = logging.INFO):
    """
    配置日志：控制台 + 文件双输出

    Args:
        log_file: 日志文件路径
        level: 日志级别
    """
    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除已有的 handler（避免重复）
    root_logger.handlers.clear()

    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件 handler
    try:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # 记录日志系统启动
        logger = logging.getLogger(__name__)
        logger.info(f"日志系统已启动，文件: {log_file}")

    except Exception as e:
        print(f"[日志轮转] 无法创建文件日志 handler: {e}")
        print("[日志轮转] 降级为仅控制台输出")
