"""
对话可调用的图片工具，复用现有文生图接口和执行表。

本文件是”语言模型决定调用工具”与”后端真实执行动作”之间的桥梁：

    list_image_models -> 查询 api_models
    txt2img           -> 校验模型和参数 -> 调用 api.generation.txt2img
"""
import logging
from pathlib import Path
from pathlib import PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from api.generation import Txt2ImgRequest, Txt2VideoRequest, txt2img, txt2video
from repositories import asset_repo, history_repo, provider_repo
from repositories.workflow_repo import WorkflowRepository
from services.seedance_tool import SeedancePromptTool

logger = logging.getLogger(__name__)


class ImageArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: int
    prompt: str = Field(min_length=1)
    n: int = Field(ge=1, le=10)
    aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4"]
    quality: Literal["low", "medium", "high"]
    regenerate: bool = False


class VideoArguments(BaseModel):
    model: int
    prompt: str = Field(min_length=1)
    ratio: Literal["16:9", "9:16", "1:1"]
    resolution: Literal["720p", "1080p"]
    duration: int = Field(ge=1, le=60)


def session_tasks(session_id: int, user_id: int) -> list:
    """读取会话任务，并用 history/assets 的持久化数据恢复最新状态。"""
    tasks = []
    for execution in WorkflowRepository.get_session_executions(session_id):
        task = execution["result"]
        if not task.get("task_id"):
            continue
        task = {**task, "execution_id": execution["id"], "status": execution["status"]}
        if task["status"] == "running":
            rows = WorkflowRepository.get_generation_result(task["history_id"], user_id)
            if rows:
                status = rows[0]["status"]
                if status in ("done", "completed"):
                    task["status"] = "completed"
                    outputs = [
                        {"url": f"/api/api-proxy/output/{PureWindowsPath(row['location']).name}", "asset_id": row["asset_id"]}
                        for row in rows if row["location"]
                    ]
                    task["videos" if task.get("media_type") == "video" else "images"] = outputs
                elif status in ("error", "failed"):
                    task["status"] = "failed"
                    task["error"] = rows[0]["message"] or "生成失败"
                else:
                    task["stage"] = status
                if task["status"] != "running":
                    WorkflowRepository.update_execution(
                        execution["id"], status=task["status"], result=task,
                        progress=100 if task["status"] == "completed" else 0,
                        error=task.get("error")
                    )
        tasks.append(task)
    if tasks:
        statuses = {task["status"] for task in tasks}
        session_status = "executing" if "running" in statuses else (
            "failed" if "failed" in statuses else "completed"
        )
        WorkflowRepository.update_session(session_id, status=session_status)
    return tasks


class WorkflowTools:
    def __init__(self, user: dict, ensure_session, generation_options: dict | None = None):
        self.user = user
        self.ensure_session = ensure_session
        self.generation_options = generation_options or {}
        self.pending_generation = None
        self.models = None
        self.video_models = None
        self.submitted = []
        self.seedance = SeedancePromptTool()

        self.tools = {
            "list_image_models": {
                "type": "function",
                "function": {
                    "name": "list_image_models",
                    "description": "查询数据库中可用于文生图的真实模型。名称、编号和提供商必须以此结果为准。",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
                "keywords": ["图片模型", "图像模型", "生图模型", "文生图", "可用模型", "image model", "txt2img"],
            },
            "txt2img": {
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
            },
            "list_video_models": {
                "type": "function",
                "function": {
                    "name": "list_video_models",
                    "description": "查询数据库中可用于文生视频的真实模型。",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
                "keywords": ["视频模型", "视频生成模型", "文生视频", "可用视频模型", "video model", "txt2video"],
            },
            "txt2video": {
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
            },
            "list_my_images": {
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
            },
            "list_my_generation_history": {
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
            },
            "generate_seedance_prompt": {
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
                    "时间戳", "剪辑节奏", "视频创作"
                ],
            },
        }
        self.handlers = {
            "list_image_models": lambda args: self.execute("list_image_models", args),
            "txt2img": lambda args: self.execute("txt2img", args),
            "list_video_models": self._list_video_models,
            "txt2video": self._txt2video,
            "list_my_images": self._list_my_images,
            "list_my_generation_history": self._list_my_generation_history,
            "generate_seedance_prompt": self._generate_seedance_prompt,
        }

    def discover(self, query: str) -> list[dict]:
        """匹配模型给出的查询词（不是用户原话），返回得分最高的三个工具。"""
        query = query.casefold()
        matches = []
        for tool in self.tools.values():
            # 每命中一个关键词加一分；没有命中的工具不提供给模型。
            score = 0
            for keyword in tool["keywords"]:
                if keyword.casefold() in query:
                    score += 1
            if score > 0:
                matches.append((score, tool))

        matches.sort(key=lambda item: item[0], reverse=True)
        return [tool for _, tool in matches[:3]]

    async def discover_and_execute(self, name: str, arguments: dict) -> dict:
        handler = self.handlers.get(name)
        if not handler:
            raise ValueError(f"不支持的工具：{name}")
        return await handler(arguments)

    async def _list_video_models(self, _arguments: dict) -> dict:
        self.video_models = [
            {key: model.get(key) for key in ("id", "name", "description", "provider")}
            for model in provider_repo.get_all_models()
            if model.get("type") == "video"
        ]
        return {"models": self.video_models}

    async def _txt2video(self, arguments: dict) -> dict:
        options = self._selected_generation_options("video", ("model", "ratio", "resolution", "duration"))
        if options is None:
            return self._request_generation_selection("video", arguments)
        args = Txt2VideoRequest(**VideoArguments.model_validate({**arguments, **options}).model_dump())
        if self.video_models is None:
            await self._list_video_models({})
        selected = next((model for model in self.video_models if model["id"] == args.model), None)
        if selected is None:
            raise ValueError("所选模型不是查询结果中的可用视频模型")
        session_id = self.ensure_session()
        definition = {"type": "txt2video", **args.model_dump()}
        for execution in WorkflowRepository.get_session_executions(session_id):
            if execution["workflow_definition"] == definition:
                if execution["result"].get("task_id"):
                    return {**execution["result"], "reused": True}
                raise ValueError("相同视频请求已存在提交记录，请先检查任务状态")
        execution_id = WorkflowRepository.create_execution(session_id, definition)
        try:
            response = await txt2video(args, user=self.user)
        except Exception as error:
            WorkflowRepository.update_execution(execution_id, status="failed", error=str(getattr(error, "detail", error)))
            raise
        task = {
            "execution_id": execution_id, "task_id": response.task_id,
            "history_id": response.history_id, "status": "running", "media_type": "video",
            "model_name": selected["name"], "parameters": args.model_dump(),
        }
        WorkflowRepository.update_execution(execution_id, current_node="txt2video", result=task)
        WorkflowRepository.update_session(session_id, intent="text_to_video", parameters=args.model_dump(), status="executing")
        self.submitted.append(task)
        return task

    async def _list_my_images(self, arguments: dict) -> dict:
        page = max(1, min(int(arguments.get("page", 1)), 1000))
        assets, total = asset_repo.get_user_assets(self.user["user_id"], "picture", None, False, page, 20)
        return {
            "total": total,
            "page": page,
            "assets": [
                {"id": item["id"], "name": Path(item["location"]).name, "url": f"/api/api-proxy/output/{Path(item['location']).name}", "created_at": str(item.get("created_at"))}
                for item in assets
            ],
        }

    async def _list_my_generation_history(self, arguments: dict) -> dict:
        page = max(1, min(int(arguments.get("page", 1)), 1000))
        type_filter = arguments.get("type")
        if type_filter:
            type_filter = "2video" if type_filter == "video" else "2img"
        rows = history_repo.list_history_with_assets(self.user["user_id"], type_filter, 20, (page - 1) * 20)
        records = {}
        for row in rows:
            item = records.setdefault(row["id"], {
                "id": row["id"], "prompt": row["prompt"], "status": row["status"],
                "type": row["type"], "model": row.get("model_name"), "created_at": str(row["created_at"]),
                "outputs": [],
            })
            if row.get("out_asset_id") and not any(output["asset_id"] == row["out_asset_id"] for output in item["outputs"]):
                filename = Path(row["out_location"]).name if row.get("out_location") else ""
                item["outputs"].append({"asset_id": row["out_asset_id"], "url": f"/api/api-proxy/output/{filename}"})
        return {"page": page, "records": list(records.values())}

    async def _generate_seedance_prompt(self, arguments: dict) -> dict:
        """生成 Seedance 视频提示词

        这个方法返回指令文本,让对话模型根据 skill 规则生成提示词。
        实际的提示词生成由对话模型完成,不是直接调用外部脚本。
        """
        request = arguments.get("request", "")
        version = arguments.get("version", "2.5")
        duration = arguments.get("duration")
        aspect_ratio = arguments.get("aspect_ratio", "16:9")

        if not request:
            return {"error": "缺少 request 参数"}

        # 判断版本
        if not version:
            version = self.seedance.determine_version(request)

        # 判断路径
        path = self.seedance.determine_path(
            user_message=request,
            duration=duration
        )

        # 生成指令
        instruction = self.seedance.generate_prompt_instruction(
            user_request=request,
            path=path,
            version=version,
            duration=duration,
            aspect_ratio=aspect_ratio
        )

        return {
            "instruction": instruction,
            "path": path,
            "version": version,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "message": f"""已生成 Seedance 视频提示词生成指令(路径 {path}, 版本 {version})。

请根据指令生成符合规范的提示词,然后:

**后续操作**:
1. 如果需要生成首帧图/角色图,请先调用 discover_tools 查找 'list_image_models',然后用 'txt2img' 生成
2. 如果需要生成视频,请先调用 discover_tools 查找 'list_video_models',然后用 'txt2video' 生成

注意: txt2img 和 txt2video 调用前必须先查询对应的模型列表。"""
        }

    async def execute(self, name: str, arguments: dict) -> dict:
        """执行语言模型请求的工具。

        ``name`` 和 ``arguments`` 来自 ConversationAgent 解析的模型 tool_call，
        因此这里必须把模型输入当成不可信数据重新校验，不能直接相信模型。
        """
        if name == "list_image_models":
            # =====【查询模型工具】=====
            # 只暴露 worker 已支持的图片模型，不返回供应商密钥或配置地址。
            # 这里读取的是数据库 api_models，不是语言模型凭空生成的模型名单。
            self.models = [
                {key: model.get(key) for key in ("id", "name", "description", "provider")}
                for model in provider_repo.get_all_models()
                if model.get("type") == "image" and model.get("provider") in ("openai", "gemini")
            ]
            logger.info("对话工具查询图片模型 count=%s", len(self.models))
            return {"models": self.models}
        if name != "txt2img":
            raise ValueError(f"不支持的工具：{name}")
        options = self._selected_generation_options("image", ("model", "n", "aspect_ratio", "quality"))
        if options is None:
            return self._request_generation_selection("image", arguments)
        if self.models is None:
            await self.execute("list_image_models", {})
        # =====【图片参数校验】=====
        # 将语言模型返回的 JSON 转成严格的 Pydantic 对象，检查类型、范围和枚举值。
        args = ImageArguments.model_validate({**arguments, **options})
        if not args.prompt.strip():
            raise ValueError("图片描述不能为空")
        selected = next((model for model in self.models if model["id"] == args.model), None)
        if selected is None:
            raise ValueError("所选模型不是查询结果中的可用图片模型，请重新选择")
        # Gemini worker 单次只生成一张，不能把数量大于一的任务提交后谎报成功。
        if selected["provider"] == "gemini" and args.n != 1:
            raise ValueError("当前 Gemini 生成接口每次支持一张图片，请改为一张")
        parameters = args.model_dump(exclude={"regenerate"})
        # =====【创建/恢复任务所属会话】=====
        session_id = self.ensure_session()
        for execution in WorkflowRepository.get_session_executions(session_id):
            if execution["workflow_definition"] == parameters and not args.regenerate:
                if execution["result"].get("task_id"):
                    return {**execution["result"], "reused": True}
                raise ValueError("相同请求已存在提交记录，请先检查生成历史；不会自动重复提交")

        # 先创建工作流执行记录，之后无论成功还是失败都能追踪这次提交。
        execution_id = WorkflowRepository.create_execution(session_id, parameters)
        try:
            # =====【真正调用文生图接口】=====
            # 这里才进入 background/api/generation.py 的 txt2img 函数。
            # 它会保存 history 并把任务放入 Redis，返回 task_id/history_id。
            response = await txt2img(Txt2ImgRequest(**parameters), user=self.user)
        except Exception as error:
            WorkflowRepository.update_execution(
                execution_id, status="failed", error=str(getattr(error, "detail", error))
            )
            raise
        # txt2img 返回的是“任务已入队”，所以这里状态是 running，图片还没有完成。
        task = {
            "execution_id": execution_id, "task_id": response.task_id,
            "history_id": response.history_id, "status": "running",
            "model_name": selected["name"], "parameters": parameters, "images": [],
        }
        WorkflowRepository.update_execution(execution_id, current_node="txt2img", result=task)
        WorkflowRepository.update_session(session_id, intent="batch_image", parameters=parameters, status="executing")
        self.submitted.append(task)
        logger.info("对话工具已提交文生图 session_id=%s execution_id=%s task_id=%s model_id=%s", session_id, execution_id, response.task_id, args.model)
        return task

    def _selected_generation_options(self, media_type: str, required: tuple[str, ...]) -> dict | None:
        options = self.generation_options
        if options.get("media_type") != media_type:
            return None
        missing = [key for key in required if options.get(key) is None]
        if missing:
            return None
        return {key: options[key] for key in required}

    def _request_generation_selection(self, media_type: str, arguments: dict) -> dict:
        providers = ("openai", "gemini") if media_type == "image" else ("ark", "openai")
        models = [
            {key: model.get(key) for key in ("id", "name", "description", "provider")}
            for model in provider_repo.get_all_models()
            if model.get("type") == media_type and model.get("provider") in providers
        ]
        self.pending_generation = {"media_type": media_type, "prompt": arguments.get("prompt", ""), "models": models}
        return {"selection_required": self.pending_generation}
