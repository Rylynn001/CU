"""通用 API 接口"""
import os
import mimetypes
from io import BytesIO
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response
from PIL import Image

from config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


@router.get("/view")
async def view_image(request: Request):
    """查看图片/视频文件"""
    query_params = request.query_params

    if "filename" not in query_params:
        return Response(status_code=404)

    filename = query_params["filename"]

    # 安全检查
    if filename.startswith('/') or '..' in filename:
        return Response(status_code=400)

    # 获取类型和目录
    file_type = query_params.get("type", "output")
    if file_type == "output":
        base_dir = settings.OUTPUT_DIR
    elif file_type == "input":
        base_dir = settings.INPUT_DIR
    elif file_type == "temp":
        base_dir = Path("/app/temp")  # 临时目录
    else:
        return Response(status_code=400)

    # 处理子文件夹
    if "subfolder" in query_params:
        subfolder = query_params["subfolder"]
        full_output_dir = base_dir / subfolder
        # 安全检查：确保不会访问目录外的文件
        try:
            full_output_dir = full_output_dir.resolve()
            base_dir = base_dir.resolve()
            if not str(full_output_dir).startswith(str(base_dir)):
                return Response(status_code=403)
        except:
            return Response(status_code=403)
        base_dir = full_output_dir

    # 获取文件名
    filename = os.path.basename(filename)
    file_path = base_dir / filename

    if not file_path.is_file():
        return Response(status_code=404)

    # 处理预览请求
    if 'preview' in query_params:
        try:
            with Image.open(file_path) as img:
                preview_info = query_params['preview'].split(';')
                image_format = preview_info[0]
                if image_format not in ['webp', 'jpeg'] or 'a' in query_params.get('channel', ''):
                    image_format = 'webp'

                quality = 90
                if preview_info[-1].isdigit():
                    quality = int(preview_info[-1])

                buffer = BytesIO()
                if image_format in ['jpeg'] or query_params.get('channel', '') == 'rgb':
                    img = img.convert("RGB")
                img.save(buffer, format=image_format, quality=quality)
                buffer.seek(0)

                return Response(
                    content=buffer.read(),
                    media_type=f'image/{image_format}',
                    headers={"Content-Disposition": f'filename="{filename}"'}
                )
        except Exception:
            return Response(status_code=500)

    # 处理通道请求
    channel = query_params.get('channel', 'rgba')

    if channel == 'rgb':
        try:
            with Image.open(file_path) as img:
                if img.mode == "RGBA":
                    r, g, b, a = img.split()
                    new_img = Image.merge('RGB', (r, g, b))
                else:
                    new_img = img.convert("RGB")

                buffer = BytesIO()
                new_img.save(buffer, format='PNG')
                buffer.seek(0)

                return Response(
                    content=buffer.read(),
                    media_type='image/png',
                    headers={"Content-Disposition": f'filename="{filename}"'}
                )
        except Exception:
            return Response(status_code=500)

    elif channel == 'a':
        try:
            with Image.open(file_path) as img:
                if img.mode == "RGBA":
                    _, _, _, a = img.split()
                else:
                    a = Image.new('L', img.size, 255)

                # alpha img
                alpha_img = Image.new('RGBA', img.size)
                alpha_img.putalpha(a)
                alpha_buffer = BytesIO()
                alpha_img.save(alpha_buffer, format='PNG')
                alpha_buffer.seek(0)

                return Response(
                    content=alpha_buffer.read(),
                    media_type='image/png',
                    headers={"Content-Disposition": f'filename="{filename}"'}
                )
        except Exception:
            return Response(status_code=500)

    # 默认：直接返回文件
    content_type = mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream'

    # 安全检查：强制某些类型下载而不是显示
    if content_type in {'text/html', 'text/html-sandboxed', 'application/xhtml+xml', 'text/javascript', 'text/css'}:
        content_type = 'application/octet-stream'

    return FileResponse(
        path=str(file_path),
        headers={
            "Content-Disposition": f'filename="{filename}"',
            "Content-Type": content_type
        }
    )
