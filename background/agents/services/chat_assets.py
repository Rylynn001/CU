"""解析聊天引用的资产，并读取模型可识别的图片内容。"""
import base64
import io
import json
import re
import subprocess
from pathlib import Path

from fastapi import HTTPException
from PIL import Image

from repositories import asset_repo


def node_reference_images(document: dict, node_id: str) -> tuple[list[int], dict[int, str]]:
    """从目标节点的实际入边和来源端口解析图片，不依赖前端提交的资产编号。"""
    nodes = {node['id']: node for node in document['nodes']}
    target = nodes.get(node_id)
    if not target or target['type'] not in ('remote-imageGenerationNode', 'remote-videoGenerationNode'):
        raise HTTPException(status_code=400, detail='提示词优化节点不存在或类型不匹配')
    image_ids = []
    for edge in document['edges']:
        if edge['target'] != node_id:
            continue
        source = nodes[edge['source']]['data']
        output = source.get('outputs', {}).get(edge.get('sourceHandle'))
        if source.get('task', {}).get('state') == 'pending':
            raise HTTPException(status_code=400, detail='上游节点正在生成，请等待完成后再反推提示词')
        if not output or output['dataType'] != 'IMAGE':
            continue
        image_ids.extend(output['value']['assetIds'])
    image_ids = list(dict.fromkeys(image_ids))
    if not image_ids:
        raise HTTPException(status_code=400, detail='请先连接有图片输出的上游节点，再反推提示词')
    if len(image_ids) > 10:
        raise HTTPException(status_code=400, detail='反推提示词最多支持 10 张上游图片')
    return image_ids, {asset_id: f'@图片{index}' for index, asset_id in enumerate(image_ids, 1)}


def load_chat_assets(asset_ids: list[int], user_id: int) -> list[dict]:
    assets = {asset["id"]: asset for asset in asset_repo.get_assets_by_ids(asset_ids)}
    result = []
    for asset_id in dict.fromkeys(asset_ids):
        asset = assets.get(asset_id)
        if not asset or asset["rfid"] != user_id:
            raise HTTPException(status_code=404, detail=f"资产 {asset_id} 不存在或无权访问")
        if asset["asset_type"] not in ("picture", "video"):
            raise HTTPException(status_code=400, detail="聊天仅支持引用图片和视频资产")
        if not Path(asset["location"]).is_file():
            raise HTTPException(status_code=404, detail=f"资产 {asset_id} 的文件不存在")
        result.append(asset)
    return result


def asset_previews(assets: list[dict]) -> list[dict]:
    return [
        {"id": asset["id"], "asset_type": asset["asset_type"],
         "url": f"/api/api-proxy/output/{Path(asset['location']).name}"}
        for asset in assets
    ]


def _image_part(data: bytes) -> dict:
    # 统一为 JPEG 并限制分辨率，避免原始大图挤占模型上下文。
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        image.thumbnail((1536, 1536))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}


def build_asset_content(message: str, assets: list[dict], asset_mentions: dict | None = None) -> str | list[dict]:
    if not assets:
        return message
    content = [{"type": "text", "text": message}]
    for asset in assets:
        mention = f"@{'视频' if asset['asset_type'] == 'video' else '图'}{asset['id']}"
        # JSON 元数据恢复后键为字符串；旧消息没有映射时继续沿用资产编号。
        mapped = (asset_mentions or {}).get(asset['id']) or (asset_mentions or {}).get(str(asset['id']))
        if mapped:
            pattern = r"@视频[1-9]\d*" if asset['asset_type'] == 'video' else r"@(?:图片|图)[1-9]\d*"
            if not re.fullmatch(pattern, mapped):
                raise HTTPException(status_code=400, detail="素材引用编号格式错误")
            mention = mapped
        label = f"{mention} 对应参考资产编号：{asset['id']}，类型：{asset['asset_type']}"
        content.append({"type": "text", "text": label})
        if asset["asset_type"] == "picture":
            content.append(_image_part(Path(asset["location"]).read_bytes()))
            continue
        # 聊天补全接口以图片接收视频画面；生成视频时仍传原始资产编号。
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", asset["location"]],
                capture_output=True, check=True, timeout=30,
            )
            duration = float(json.loads(probe.stdout)["format"]["duration"])
            for index in range(6):
                timestamp = duration * index / 6
                frame = subprocess.run(
                    ["ffmpeg", "-v", "error", "-ss", str(timestamp), "-i", asset["location"],
                     "-frames:v", "1", "-vf", "scale=768:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
                    capture_output=True, check=True, timeout=30,
                )
                content.append({"type": "text", "text": f"视频画面 {timestamp:.2f} 秒（总时长 {duration:.2f} 秒，不含音频）"})
                content.append(_image_part(frame.stdout))
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            raise HTTPException(status_code=400, detail=f"视频资产 {asset['id']} 无法读取画面，请检查文件及 ffmpeg/ffprobe") from error
    return content
