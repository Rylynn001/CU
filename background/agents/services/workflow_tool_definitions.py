"""对话 Agent 可发现的工具定义。"""
from enum import Enum


class WorkflowTool(Enum):
    DISCOVER_TOOLS = {
        "type": "function",
        "function": {
            "name": "discover_tools",
            "description": "根据用户当前需求，在后端能力目录中查找相关工具。请用自然语言描述要完成的事，不要猜测工具名。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "用户想完成的事情或要查询的信息"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        "keywords": [],
    }
    IMG2IMG = {
        "type": "function",
        "function": {
            "name": "img2img",
            "description": "使用用户在当前画布中引用或检索到的图片资产生成或编辑图片。调用前查询图片模型，生成参数由用户在弹窗确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "图片内容或修改要求"},
                    "input_asset_ids": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "description": "当前画布中用户引用的图片资产编号"},
                },
                "required": ["prompt", "input_asset_ids"],
                "additionalProperties": False,
            },
        },
        "keywords": ["图生图", "参考图片生成图片", "参考图", "编辑图片", "修改图片", "img2img", "image to image"],
    }
    IMG2VIDEO = {
        "type": "function",
        "function": {
            "name": "img2video",
            "description": "使用用户在当前画布中引用或检索到的图片、视频资产生成视频。调用前查询视频模型，生成参数由用户在弹窗确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "视频内容描述"},
                    "input_asset_ids": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "description": "当前画布中用户引用的图片或视频资产编号"},
                },
                "required": ["prompt", "input_asset_ids"],
                "additionalProperties": False,
            },
        },
        "keywords": ["图生视频", "参考图片生成视频", "参考图", "参考视频", "视频生视频", "img2video", "image to video"],
    }
    LIST_IMAGE_MODELS = {
        "type": "function",
        "function": {
            "name": "list_image_models",
            "description": "查询数据库中可用于文生图的真实模型。名称、编号和提供商必须以此结果为准。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        "keywords": ["图片模型", "图像模型", "生图模型", "文生图", "可用模型", "image model", "txt2img"],
    }
    TXT2IMG = {
        "type": "function",
        "function": {
            "name": "txt2img",
            "description": "按用户要求提交文生图任务。调用前必须查询图片模型，并确认用户选定的模型。",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "integer", "description": "list_image_models 返回的模型编号"},
                    "prompt": {"type": "string", "description": "图片内容描述"},
                    "n": {"type": "integer", "minimum": 1, "maximum": 10},
                    "aspect_ratio": {"type": "string", "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"]},
                    "quality": {"type": "string", "enum": ["low", "medium", "high"]},
                    "regenerate": {"type": "boolean", "default": False},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
        "keywords": ["生成图片", "生成一张图", "画一张", "画图", "生图", "图片创作", "图片生成", "image generation", "txt2img"],
    }
    LIST_VIDEO_MODELS = {
        "type": "function",
        "function": {
            "name": "list_video_models",
            "description": "查询数据库中可用于文生视频的真实模型。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        "keywords": ["视频模型", "视频生成模型", "文生视频", "可用视频模型", "video model", "txt2video"],
    }
    TXT2VIDEO = {
        "type": "function",
        "function": {
            "name": "txt2video",
            "description": "按用户要求提交文生视频任务。调用前必须查询视频模型，并确认用户选定的模型。",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "integer", "description": "list_video_models 返回的模型编号"},
                    "prompt": {"type": "string", "description": "视频内容描述"},
                    "ratio": {"type": "string", "enum": ["16:9", "9:16", "1:1"]},
                    "resolution": {"type": "string", "enum": ["720p", "1080p"]},
                    "duration": {"type": "integer", "minimum": 1, "maximum": 60},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
        "keywords": ["生成视频", "生成一段视频", "生一段视频", "做一段视频", "做个视频", "制作视频", "文生视频", "视频创作", "video generation", "txt2video"],
    }
    LIST_MY_IMAGES = {
        "type": "function",
        "function": {
            "name": "list_my_images",
            "description": "查询当前用户最近的图片资产。",
            "parameters": {
                "type": "object",
                "properties": {"page": {"type": "integer", "minimum": 1, "default": 1}},
                "additionalProperties": False,
            },
        },
        "keywords": ["我的图片", "图片查询", "查图片", "找图片", "图片资产", "最近图片", "my images", "image search"],
    }
    LIST_MY_GENERATION_HISTORY = {
        "type": "function",
        "function": {
            "name": "list_my_generation_history",
            "description": "查询当前用户最近的图片和视频生成历史。",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["image", "video"]},
                    "page": {"type": "integer", "minimum": 1, "default": 1},
                },
                "additionalProperties": False,
            },
        },
        "keywords": ["生成历史", "任务历史", "历史记录", "之前生成", "生成记录", "my history", "generation history"],
    }
    SEARCH_SESSION_REFERENCE_ASSETS = {
        "type": "function",
        "function": {
            "name": "search_session_reference_assets",
            "description": "在当前画布节点中搜索引用或生成的图片，按提示词关键词匹配并返回资产编号。可在该画布的不同会话之间复用，不搜索其他画布。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "maxItems": 8, "description": "当前画布节点提示词中的主体或场景关键词"},
                },
                "required": ["keywords"],
                "additionalProperties": False,
            },
        },
        "keywords": ["之前引入的图片", "当前画布之前的图片", "本画布之前图片", "本画布参考图", "之前消息中的图片", "找回本画布图片", "参考之前图片", "session reference assets"],
    }
    GENERATE_SEEDANCE_PROMPT = {
        "type": "function",
        "function": {
            "name": "generate_seedance_prompt",
            "description": "生成符合字节跳动即梦(Seedance)平台规范的专业视频提示词。此工具包含完整的平台规则、时间戳分镜、运镜编码、美学约束等专业方法论。用户提到视频提示词、视频脚本、短剧、分镜等需求时必须调用此工具，不能自行生成。支持 2.0(15秒) 和 2.5(30秒直出,最长180秒)版本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {"type": "string", "description": "用户的视频创意需求描述"},
                    "version": {"type": "string", "enum": ["2.0", "2.5"], "default": "2.5", "description": "Seedance版本"},
                    "duration": {"type": "integer", "minimum": 4, "maximum": 180, "description": "目标时长(秒)"},
                    "aspect_ratio": {"type": "string", "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"], "default": "16:9"},
                },
                "required": ["request"],
                "additionalProperties": False,
            },
        },
        "keywords": [
            "seedance", "即梦", "视频提示词", "短剧", "视频生成", "AI视频",
            "小云雀", "豆包", "30秒视频", "长视频", "视频脚本",
            "运镜", "镜头", "分镜", "剪辑", "图生视频", "赛博朋克",
            "时间戳", "剪辑节奏", "视频创作",
        ],
    }
