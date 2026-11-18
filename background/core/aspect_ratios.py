"""产品比例、旧参数兼容及上游参数转换。"""
from math import gcd
from typing import Literal, get_args

ImageAspectRatio = Literal['1:1', '16:9', '9:16', '21:9', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', 'auto']
VideoAspectRatio = Literal['16:9', '4:3', '1:1', '3:4', '9:16', '21:9', 'auto']
IMAGE_ASPECT_RATIOS = get_args(ImageAspectRatio)
VIDEO_ASPECT_RATIOS = get_args(VideoAspectRatio)
OPENAI_IMAGE_SIZES = {
    '1:1': '1024x1024', '16:9': '1536x864', '9:16': '864x1536',
    '21:9': '1792x768', '2:3': '1024x1536', '3:2': '1536x1024',
    '3:4': '960x1280', '4:3': '1280x960', '4:5': '1024x1280',
    '5:4': '1280x1024', 'auto': 'auto',
}


def normalize_parameters(media_type: str, parameters: dict) -> dict:
    """旧字段只在边界兼容；新任务只保存 aspect_ratio。"""
    result = dict(parameters or {})
    size = result.pop('size', None)
    ratio = result.pop('ratio', None)
    if 'aspect_ratio' not in result:
        if media_type == 'image' and size is not None:
            if size == 'auto':
                ratio = 'auto'
            else:
                try:
                    width, height = map(int, str(size).split('x'))
                    divisor = gcd(width, height)
                    ratio = f'{width // divisor}:{height // divisor}' if width > 0 and height > 0 else ''
                except (ValueError, ZeroDivisionError):
                    raise ValueError(f'无效的历史图片尺寸: {size}') from None
                # 21:9 的约分结果是 7:3。
                ratio = '21:9' if ratio == '7:3' else ratio
        result['aspect_ratio'] = ratio if ratio is not None else ('1:1' if media_type == 'image' else '16:9')
    if media_type == 'video' and result['aspect_ratio'] == 'adaptive':
        result['aspect_ratio'] = 'auto'
    allowed = IMAGE_ASPECT_RATIOS if media_type == 'image' else VIDEO_ASPECT_RATIOS
    if result['aspect_ratio'] not in allowed:
        raise ValueError(f'不支持的{"图片" if media_type == "image" else "视频"}比例: {result["aspect_ratio"]}')
    return result


def provider_parameters(media_type: str, provider: str, model: str, parameters: dict) -> dict:
    result = normalize_parameters(media_type, parameters)
    ratio = result.pop('aspect_ratio')
    if media_type == 'video':
        result['ratio'] = 'adaptive' if ratio == 'auto' else ratio
    elif provider == 'openai':
        size = OPENAI_IMAGE_SIZES[ratio]
        if not model.lower().startswith('gpt-image-2') and size not in {'auto', '1024x1024', '1536x1024', '1024x1536'}:
            raise ValueError(f'模型 {model} 未支持自定义尺寸，无法原生生成 {ratio} 图片，请选择 GPT Image 2 或其他支持此比例的模型')
        result['size'] = size
    elif provider == 'gemini':
        # 公共图片面板的质量档位不属于 Gemini ImageConfig 参数。
        result.pop('quality', None)
        if ratio != 'auto':
            result['aspect_ratio'] = ratio
    return result


def model_parameter_config(media_type: str, config: dict | None) -> dict:
    """只替换比例字段，保留模型其他参数和参考素材能力。"""
    result = dict(config or {})
    fields = [field for field in result.get('fields', []) if field.get('key') not in {'aspect_ratio', 'ratio', 'size'}]
    result['fields'] = [{
        'key': 'aspect_ratio', 'label': '比例', 'type': 'select',
        'default': '1:1' if media_type == 'image' else '16:9',
        'options': list(IMAGE_ASPECT_RATIOS if media_type == 'image' else VIDEO_ASPECT_RATIOS),
    }, *fields]
    return result
