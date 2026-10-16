"""资产管理相关路由"""
import uuid
import pathlib
import subprocess
import asyncio
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.auth import get_current_user
from config import settings
from repositories import asset_repo

router = APIRouter()


# ── 文件服务 ──────────────────────────────────────────────────────────────

@router.get('/output/{filename}')
async def serve_output_file(filename: str):
    """提供输出文件服务"""
    # 安全检查：防止路径遍历和路径分隔符
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail='Invalid filename')

    file_path = pathlib.Path(settings.OUTPUT_DIR) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail='File not found')

    return FileResponse(file_path)


@router.get('/view')
async def serve_view_file(filename: str, type: str = 'output'):
    """提供文件预览服务(兼容 ComfyUI 的 /view 接口)"""
    # 安全检查：防止路径遍历
    if '..' in filename:
        raise HTTPException(status_code=400, detail='Invalid filename')

    # 提取纯文件名（去掉路径前缀）
    clean_filename = pathlib.Path(filename.replace('\\', '/')).name
    if not clean_filename:
        raise HTTPException(status_code=400, detail='Invalid filename')

    file_path = pathlib.Path(settings.OUTPUT_DIR) / clean_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail='File not found')

    return FileResponse(file_path)


# 文件验证配置
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv'}

IMAGE_MAGIC_BYTES = {
    b'\xFF\xD8\xFF': 'jpg',
    b'\x89PNG\r\n\x1a\n': 'png',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
    b'RIFF': 'webp',
    b'BM': 'bmp',
}

VIDEO_MAGIC_BYTES = {
    b'\x00\x00\x00\x18ftypmp4': 'mp4',
    b'\x00\x00\x00\x1cftypisom': 'mp4',
    b'RIFF': 'avi',
    b'\x1aE\xdf\xa3': 'mkv',
    b'FLV': 'flv',
}


def validate_image_file(file_bytes: bytes, filename: str) -> tuple[bool, str]:
    """验证图片文件"""
    if len(file_bytes) > 1024 * 1024 * 1024:
        return False, '文件大小不能超过 1GB'
    if len(file_bytes) < 10:
        return False, '文件内容过小'

    ext = pathlib.Path(filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return False, f'不支持的图片格式 {ext}'

    # 检查文件头
    for magic, _ in IMAGE_MAGIC_BYTES.items():
        if file_bytes.startswith(magic):
            if magic == b'RIFF' and len(file_bytes) >= 12:
                if file_bytes[8:12] == b'WEBP':
                    return True, ''
            else:
                return True, ''

    return False, '文件内容不是有效的图片格式'


def validate_video_file(file_bytes: bytes, filename: str) -> tuple[bool, str]:
    """验证视频文件"""
    if len(file_bytes) > 1024 * 1024 * 1024:
        return False, '文件大小不能超过 1GB'
    if len(file_bytes) < 100:
        return False, '文件内容过小'

    ext = pathlib.Path(filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        return False, f'不支持的视频格式 {ext}'

    file_head = file_bytes[:32]
    for magic, _ in VIDEO_MAGIC_BYTES.items():
        if file_head.startswith(magic):
            return True, ''
        if b'ftyp' in file_head[:32]:
            return True, ''

    return False, '文件内容不是有效的视频格式'


@router.get("/user/assets")
async def get_user_assets(
    current_user: dict = Depends(get_current_user),
    asset_type: str = None,
    tag: int = None,
    favorite: str = None,
    page: int = Query(1, ge=1)
):
    """获取用户资产列表"""
    user_id = current_user['user_id']
    page_size = 30

    # 转换favorite为bool
    favorite_bool = (favorite == '1')

    assets, total = asset_repo.get_user_assets(user_id, tag, favorite_bool, page, page_size)

    return {'assets': assets, 'total': total, 'page': page, 'page_size': page_size}


@router.post("/user/assets/{asset_id}/favorite")
async def set_asset_favorite(
    asset_id: int,
    tag: int,
    current_user: dict = Depends(get_current_user)
):
    """设置资产标签"""
    user_id = current_user['user_id']

    if tag not in (0, 1, 2, 3, 4):
        raise HTTPException(status_code=400, detail='tag 必须是 0-4')

    result = asset_repo.update_asset_tag(asset_id, user_id, tag)

    if result == 0:
        raise HTTPException(status_code=404, detail='资产不存在或无权限')

    return {'ok': True}


@router.post("/upload/file")
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """通用文件上传"""
    user_id = current_user['user_id']
    file_bytes = await file.read()
    filename = file.filename or 'upload'

    # 验证文件类型
    is_image_valid, image_error = validate_image_file(file_bytes, filename)
    if is_image_valid:
        asset_type = 'picture'
        ext = pathlib.Path(filename).suffix.lower() or '.png'
    else:
        is_video_valid, video_error = validate_video_file(file_bytes, filename)
        if is_video_valid:
            asset_type = 'video'
            ext = pathlib.Path(filename).suffix.lower() or '.mp4'
        else:
            raise HTTPException(
                status_code=400,
                detail=f'不支持的文件类型。图片错误：{image_error}；视频错误：{video_error}'
            )

    # 保存文件
    unique_filename = f'{uuid.uuid4().hex}{ext}'
    file_path = settings.OUTPUT_DIR / unique_filename

    with open(file_path, 'wb') as f:
        f.write(file_bytes)

    # 保存到数据库
    asset_id = asset_repo.create_asset(str(file_path), user_id, asset_type)

    return {'id': asset_id, 'location': str(file_path), 'asset_type': asset_type}


@router.get("/upload/image/{asset_id}/b64")
async def get_input_image_b64(asset_id: int):
    """获取资产的 base64 编码"""
    import base64

    result = fetch_one(
        'SELECT location FROM assets WHERE id = %s',
        (asset_id,)
    )

    if not result:
        raise HTTPException(status_code=404, detail=f'asset {asset_id} not found')

    file_path = pathlib.Path(result['location'])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f'file not found: {result["location"]}')

    b64 = base64.b64encode(file_path.read_bytes()).decode()
    return {'b64': b64, 'location': result['location']}


class AssetByIdsRequest(BaseModel):
    ids: list[int]


@router.post("/assets/by-ids")
async def get_assets_by_ids(request: AssetByIdsRequest):
    """批量获取资产"""
    assets = asset_repo.get_assets_by_ids(request.ids)
    return {'assets': assets}


@router.post("/extract-frame")
async def extract_frame(
    asset_id: int,
    time_sec: float,
    current_user: dict = Depends(get_current_user)
):
    """从视频提取帧"""
    user_id = current_user['user_id']

    asset = asset_repo.get_asset_by_id(asset_id)

    if not asset:
        raise HTTPException(status_code=404, detail='资产不存在')

    video_path = pathlib.Path(asset['location'])
    if not video_path.is_absolute():
        video_path = settings.OUTPUT_DIR / video_path.name

    if not video_path.exists():
        raise HTTPException(status_code=404, detail='视频文件不存在')

    out_filename = f'frame_{uuid.uuid4().hex[:12]}.png'
    out_path = settings.OUTPUT_DIR / out_filename

    cmd = [
        'ffmpeg', '-y',
        '-ss', str(time_sec),
        '-i', str(video_path),
        '-frames:v', '1',
        str(out_path),
    ]

    try:
        await asyncio.to_thread(
            subprocess.run, cmd, check=True, capture_output=True
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail='ffmpeg 抽帧失败')

    new_id = asset_repo.create_asset(str(out_path), user_id, 'picture')

    return {'ok': True, 'asset_id': new_id, 'filename': out_filename}
