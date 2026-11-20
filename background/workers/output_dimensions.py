"""读取生成文件真实尺寸；明显偏离时保留结果并给出提示。"""
import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def check_dimensions(task_id: str, path: Path, aspect_ratio: str, media_type: str = 'image', *, expected_size: str | None = None) -> dict:
    try:
        if media_type == 'image':
            from PIL import Image
            with Image.open(path) as image:
                width, height = image.size
        else:
            ffprobe = shutil.which('ffprobe')
            if not ffprobe:
                logger.warning('[%s] 未找到 ffprobe，无法读取视频真实尺寸', task_id)
                return {}
            output = subprocess.run(
                [ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'json', str(path)],
                capture_output=True, text=True, check=True, timeout=15,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            stream = json.loads(output.stdout)['streams'][0]
            width, height = stream['width'], stream['height']
    except Exception as error:
        logger.warning('[%s] 无法读取生成文件尺寸: %s', task_id, error)
        return {}

    metadata = {'width': width, 'height': height}
    logger.info('[%s] 生成结果尺寸: requested_aspect_ratio=%s width=%s height=%s', task_id, aspect_ratio, width, height)
    if expected_size and expected_size != 'auto':
        expected_width, expected_height = map(int, expected_size.split('x'))
        if (width, height) != (expected_width, expected_height):
            metadata['warning'] = f'所选尺寸为 {expected_width}×{expected_height}，上游返回尺寸为 {width}×{height}，尺寸不符；已保留原始结果，请检查模型或中转服务是否支持该参数。'
            logger.warning('[%s] %s', task_id, metadata['warning'])
            return metadata
    if aspect_ratio != 'auto':
        expected_width, expected_height = map(int, aspect_ratio.split(':'))
        # 允许模型编码网格造成的约 1% 误差。
        if abs(width * expected_height / (height * expected_width) - 1) > 0.01:
            metadata['warning'] = f'所选比例为 {aspect_ratio}，上游返回尺寸为 {width}×{height}，比例不符；已保留原始结果，请检查模型或中转服务是否支持该参数。'
            logger.warning('[%s] %s', task_id, metadata['warning'])
    return metadata
