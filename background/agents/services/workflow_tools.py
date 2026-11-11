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
from .seedance_tool import SeedancePromptTool
from .workflow_tool_definitions import WorkflowTool
from .chat_assets import load_chat_assets

logger = logging.getLogger(__name__)


class ImageArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: int
    prompt: str = Field(min_length=1)
    n: int = Field(ge=1, le=10)
    aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4"]
    quality: Literal["low", "medium", "high"]
    regenerate: bool = False
    input_asset_ids: list[int] = Field(default_factory=list)


class VideoArguments(BaseModel):
    model: int
    prompt: str = Field(min_length=1)
    ratio: Literal["16:9", "9:16", "1:1"]
    resolution: Literal["720p", "1080p"]
    duration: int = Field(ge=1, le=60)
    input_asset_ids: list[int] | None = None


def session_tasks(session_id: int, user_id: int) -> list:
    """读取会话任务，并用 history/assets 的持久化数据恢复最新状态。"""
    tasks = []
    for execution in WorkflowRepository.get_session_executions(session_id):
        task = execution["result"]
        if not task.get("task_id"):
            continue
        task = {
            **task,
            "execution_id": execution["id"],
            "conversation_id": execution.get("conversation_id"),
            "status": execution["status"],
        }
        if task["status"] in ("running", "completed") and task.get("history_id"):
            rows = WorkflowRepository.get_generation_result(task["history_id"], user_id)
            if rows:
                status = rows[0]["status"]
                if status in ("done", "completed"):
                    task["status"] = "completed"
                    output_asset_ids = [row["asset_id"] for row in rows if row["asset_id"] is not None]
                    WorkflowRepository.add_conversation_assets(
                        task.get("conversation_id"), session_id, user_id, output_asset_ids
                    )
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
    def __init__(self, user: dict, ensure_session, generation_options: dict | None = None, ensure_conversation=None):
        self.user = user
        self.ensure_session = ensure_session
        self.ensure_conversation = ensure_conversation
        self.generation_options = generation_options or {}
        self.pending_generation = None
        self.models = None
        self.video_models = None
        self.submitted = []
        self.asset_ids = []
        self.allowed_asset_ids = set()
        self.seedance = SeedancePromptTool()

        self.tools = {
            tool.value["function"]["name"]: tool.value
            for tool in WorkflowTool
            if tool is not WorkflowTool.DISCOVER_TOOLS
        }
        self.handlers = {
            WorkflowTool.IMG2IMG.value["function"]["name"]: lambda args: self.execute(WorkflowTool.IMG2IMG.value["function"]["name"], args),
            WorkflowTool.IMG2VIDEO.value["function"]["name"]: self._img2video,
            WorkflowTool.LIST_IMAGE_MODELS.value["function"]["name"]: lambda args: self.execute(WorkflowTool.LIST_IMAGE_MODELS.value["function"]["name"], args),
            WorkflowTool.TXT2IMG.value["function"]["name"]: lambda args: self.execute(WorkflowTool.TXT2IMG.value["function"]["name"], args),
            WorkflowTool.LIST_VIDEO_MODELS.value["function"]["name"]: self._list_video_models,
            WorkflowTool.TXT2VIDEO.value["function"]["name"]: self._txt2video,
            WorkflowTool.LIST_MY_IMAGES.value["function"]["name"]: self._list_my_images,
            WorkflowTool.LIST_MY_GENERATION_HISTORY.value["function"]["name"]: self._list_my_generation_history,
            WorkflowTool.SEARCH_SESSION_REFERENCE_ASSETS.value["function"]["name"]: self._search_session_reference_assets,
            WorkflowTool.GENERATE_SEEDANCE_PROMPT.value["function"]["name"]: self._generate_seedance_prompt,
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
        found = [tool for _, tool in matches[:3]]
        if any(tool["function"]["name"] == WorkflowTool.IMG2VIDEO.value["function"]["name"] for tool in found):
            search_tool = WorkflowTool.SEARCH_SESSION_REFERENCE_ASSETS.value
            if not any(tool["function"]["name"] == search_tool["function"]["name"] for tool in found):
                found.append(search_tool)
        return found

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
        input_asset_ids = self._input_assets(arguments, "video")
        if input_asset_ids:
            arguments = {**arguments, "input_asset_ids": input_asset_ids}
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
        conversation_id = self.ensure_conversation() if self.ensure_conversation else None
        execution_id = WorkflowRepository.create_execution(session_id, definition, conversation_id)
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
        WorkflowRepository.update_session(session_id, intent="text_to_video", parameters={}, status="executing")
        self.submitted.append(task)
        return task

    async def _img2video(self, arguments: dict) -> dict:
        if not arguments.get("input_asset_ids", self.asset_ids):
            raise ValueError("请先引入参考图片或视频资产")
        return await self._txt2video(arguments)

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

    async def _search_session_reference_assets(self, arguments: dict) -> dict:
        keywords = arguments.get("keywords")
        if not isinstance(keywords, list) or not 1 <= len(keywords) <= 8 or any(not isinstance(word, str) or not word.strip() for word in keywords):
            raise ValueError("请提供图片描述关键词")
        session_id = self.ensure_session()
        messages = WorkflowRepository.get_session_asset_messages(session_id, self.user["user_id"])
        keywords = list(dict.fromkeys(word.strip().casefold() for word in keywords))
        matching_messages = [
            message for message in messages
            if any(keyword in message["message"].casefold() for keyword in keywords)
        ]
        asset_ids = list(dict.fromkeys(
            asset_id for message in matching_messages for asset_id in message["asset_ids"]
        ))
        assets = {
            asset["id"]: asset for asset in asset_repo.get_assets_by_ids(asset_ids)
            if asset["rfid"] == self.user["user_id"] and asset["asset_type"] == "picture"
        }
        records = {}
        for index, message in enumerate(matching_messages):
            record = records.setdefault(index, {
                "message": message["message"], "assets": [],
            })
            for asset_id in message["asset_ids"]:
                asset = assets.get(asset_id)
                if asset and not any(item["id"] == asset_id for item in record["assets"]):
                    self.allowed_asset_ids.add(asset_id)
                    record["assets"].append({
                        "id": asset_id, "type": asset["asset_type"],
                        "url": f"/api/api-proxy/output/{Path(asset['location']).name}",
                    })
        return {"keywords": keywords, "records": [record for record in records.values() if record["assets"]]}

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
        if name not in ("txt2img", "img2img"):
            raise ValueError(f"不支持的工具：{name}")
        input_asset_ids = self._input_assets(arguments, "image")
        if name == "img2img" and not input_asset_ids:
            raise ValueError("请先引入参考图片资产")
        if input_asset_ids:
            arguments = {**arguments, "input_asset_ids": input_asset_ids}
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
        parameters = args.model_dump(exclude={"regenerate", "input_asset_ids"})
        if input_asset_ids:
            parameters["input_asset_ids"] = input_asset_ids
        # =====【创建/恢复任务所属会话】=====
        session_id = self.ensure_session()
        for execution in WorkflowRepository.get_session_executions(session_id):
            if execution["workflow_definition"] == parameters and not args.regenerate:
                if execution["result"].get("task_id"):
                    return {**execution["result"], "reused": True}
                raise ValueError("相同请求已存在提交记录，请先检查生成历史；不会自动重复提交")

        # 先创建工作流执行记录，之后无论成功还是失败都能追踪这次提交。
        conversation_id = self.ensure_conversation() if self.ensure_conversation else None
        execution_id = WorkflowRepository.create_execution(session_id, parameters, conversation_id)
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
        WorkflowRepository.update_session(session_id, intent="batch_image", parameters={}, status="executing")
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
        input_asset_ids = arguments.get("input_asset_ids", [])
        providers = ("openai", "gemini") if media_type == "image" else ("ark", "openai")
        models = [
            {key: model.get(key) for key in ("id", "name", "description", "provider")}
            for model in provider_repo.get_all_models()
            if model.get("type") == media_type and model.get("provider") in providers
        ]
        self.pending_generation = {"media_type": media_type, "prompt": arguments.get("prompt", ""), "models": models}
        if input_asset_ids:
            self.pending_generation.update({
                "tool_name": "img2img" if media_type == "image" else "img2video",
                "input_asset_ids": input_asset_ids,
            })
        return {"selection_required": self.pending_generation}

    def _input_assets(self, arguments: dict, media_type: str) -> list[int]:
        asset_ids = arguments.get("input_asset_ids", self.asset_ids)
        if not isinstance(asset_ids, list) or any(type(asset_id) is not int for asset_id in asset_ids):
            raise ValueError("参考资产编号必须是整数列表")
        # 即使模型没先调用检索工具，也只接受当前会话用户消息实际引用过的编号。
        session_messages = WorkflowRepository.get_session_asset_messages(
            self.ensure_session(), self.user["user_id"],
        ) if asset_ids else []
        session_asset_ids = {
            asset_id for message in session_messages for asset_id in message["asset_ids"]
        }
        self.allowed_asset_ids.update(session_asset_ids)
        unavailable_ids = sorted(set(asset_ids) - self.allowed_asset_ids)
        if unavailable_ids:
            raise ValueError(
                f"资产 {unavailable_ids} 未关联到当前会话消息，请先在本会话引入这些图片"
            )
        assets = load_chat_assets(asset_ids, self.user["user_id"]) if asset_ids else []
        if media_type == "image" and any(asset["asset_type"] != "picture" for asset in assets):
            raise ValueError("生成图片仅支持参考图片，请移除视频资产")
        return [asset["id"] for asset in assets]
