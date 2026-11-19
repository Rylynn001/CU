"""助手生成工具：统一模型选择、参数确认和单次/多步任务提交。"""
import uuid
from pathlib import Path
from typing import Literal
from core.aspect_ratios import ImageAspectRatio, VideoAspectRatio

from pydantic import BaseModel, ConfigDict, Field
from repositories import asset_repo, history_repo, provider_repo, canvas_repo
from repositories.workflow_repo import WorkflowRepository
from .seedance_tool import SeedancePromptTool
from .workflow_tool_definitions import WorkflowTool
from .chat_assets import load_chat_assets
from .canvas_tasks import submit_generation, refresh_tasks
from .generation_plan import GenerationPlan

class ImageArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: int
    prompt: str = Field(min_length=1)
    n: int = Field(ge=1, le=10)
    aspect_ratio: ImageAspectRatio
    quality: Literal["low", "medium", "high"]
    regenerate: bool = False
    input_asset_ids: list[int] = Field(default_factory=list)


class VideoArguments(BaseModel):
    model: int
    prompt: str = Field(min_length=1)
    aspect_ratio: VideoAspectRatio
    resolution: Literal["480p", "720p", "1080p", "4k"]
    duration: int = Field(ge=1, le=60)
    input_asset_ids: list[int] | None = None


def session_tasks(session_id: int, user_id: int) -> list:
    """读取会话任务，并用 history/assets 的持久化数据恢复最新状态。"""
    tasks = refresh_tasks(WorkflowRepository.get_session_executions(session_id), user_id)
    if tasks:
        statuses = {task["status"] for task in tasks}
        session_status = "executing" if statuses & {"running", "queued", "submitting"} else (
            "failed" if "failed" in statuses else "completed"
        )
        WorkflowRepository.update_session(session_id, status=session_status)
    return tasks


class WorkflowTools:
    def __init__(self, user: dict, ensure_session, generation_options: dict | None = None, ensure_conversation=None, *, canvas_id: int):
        self.user = user
        self.canvas_id = canvas_id
        self.on_canvas_change = None
        self.ensure_session = ensure_session
        self.ensure_conversation = ensure_conversation
        self.generation_options = generation_options or {}
        self.pending_generation = None
        self.model_catalog = None
        self.submitted = []
        self.asset_ids = []
        self.asset_mentions = {}
        self.allowed_asset_ids = set()
        self.seedance = SeedancePromptTool()

        self.tools = {
            tool.value["function"]["name"]: tool.value
            for tool in WorkflowTool
            if tool is not WorkflowTool.DISCOVER_TOOLS
        }
        self.handlers = {
            'list_my_images': self._list_my_images,
            'list_my_generation_history': self._list_my_generation_history,
            'search_session_reference_assets': self._search_session_reference_assets,
            'generate_seedance_prompt': self._generate_seedance_prompt,
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
        match name:
            case 'txt2img' | 'img2img':
                return await self._generate('image', name, arguments)
            case 'txt2video' | 'img2video':
                return await self._generate('video', name, arguments)
            case 'list_image_models':
                return {'models': self._models('image')}
            case 'list_video_models':
                return {'models': self._models('video')}
            case 'generation_plan':
                return self._request_plan(arguments)
            case _:
                handler = self.handlers.get(name)
                if not handler:
                    raise ValueError(f'不支持的工具：{name}')
                return await handler(arguments)

    def _models(self, media_type: str) -> list[dict]:
        if self.model_catalog is None:
            self.model_catalog = provider_repo.get_all_models()
        providers = ('openai', 'gemini') if media_type == 'image' else ('ark', 'openai')
        return [
            {key: model.get(key) for key in ('id', 'name', 'description', 'provider', 'parameters')}
            for model in self.model_catalog
            if model.get('type') == media_type and model.get('provider') in providers
        ]

    def generation_parameters(self, media_type: str, arguments: dict, options: dict) -> tuple[dict, dict]:
        schema = ImageArguments if media_type == 'image' else VideoArguments
        keys = ('model', 'n', 'aspect_ratio', 'quality') if media_type == 'image' else ('model', 'aspect_ratio', 'resolution', 'duration')
        selected_options = dict(options)
        if media_type == 'video' and 'aspect_ratio' not in selected_options and 'ratio' in selected_options:
            selected_options['aspect_ratio'] = 'auto' if selected_options['ratio'] == 'adaptive' else selected_options['ratio']
        args = schema.model_validate({**arguments, **{key: selected_options[key] for key in keys if key in selected_options}})
        if not args.prompt.strip():
            raise ValueError('生成描述不能为空')
        selected = next((model for model in self._models(media_type) if model['id'] == args.model), None)
        if selected is None:
            raise ValueError('所选生成模型不可用，请重新选择')
        if media_type == 'image' and selected['provider'] == 'gemini' and args.n != 1:
            raise ValueError('当前 Gemini 生成接口每次支持一张图片，请改为一张')
        return args.model_dump(exclude={'regenerate'}, exclude_none=True), selected

    async def _generate(self, media_type: str, name: str, arguments: dict) -> dict:
        input_asset_ids = self._input_assets(arguments, media_type)
        if name in ('img2img', 'img2video') and not input_asset_ids:
            raise ValueError('请先引入参考素材')
        arguments = {**arguments, 'input_asset_ids': input_asset_ids,
                     'prompt': self._reference_prompt(arguments['prompt'], input_asset_ids)}
        keys = ('model', 'n', 'aspect_ratio', 'quality') if media_type == 'image' else ('model', 'aspect_ratio', 'resolution', 'duration')
        options = self._selected_generation_options(media_type, keys)
        if options is None:
            return self._request_generation_selection(media_type, arguments)
        parameters, selected = self.generation_parameters(media_type, arguments, options)
        session_id = self.ensure_session()
        task = await submit_generation(
            self.user, self.canvas_id, media_type, parameters, session_id=session_id,
            conversation_id=self.ensure_conversation() if self.ensure_conversation else None,
            model_name=selected['name'], on_change=self.on_canvas_change,
        )
        WorkflowRepository.update_session(session_id, intent='batch_image' if media_type == 'image' else 'text_to_video', parameters={}, status='executing')
        self.submitted.append(task)
        return task

    def _request_plan(self, arguments: dict) -> dict:
        # 这里仅暂存并返回参数选择数据；只有确认接口调用 confirm_plan 才创建节点和执行记录。
        plan = GenerationPlan.model_validate(arguments)
        for step in plan.steps:
            step.input_asset_ids = self._input_assets({'input_asset_ids': step.input_asset_ids}, step.media_type)
            step.prompt = self._reference_prompt(step.prompt, step.input_asset_ids)
        self.pending_generation = {
            'media_type': 'plan', 'plan_id': str(uuid.uuid4()),
            'prompt': '按以下步骤依次生成', 'steps': plan.model_dump(exclude_none=True)['steps'],
            'models_by_type': {kind: self._models(kind) for kind in {step.media_type for step in plan.steps}},
        }
        return {'selection_required': self.pending_generation}

    async def confirm_plan(self, pending: dict) -> dict:
        # 用户确认模型及参数后，统一验证每一步并将计划写入数据库等待后台调度。
        from repositories import generation_plan_repo
        from api.generation import validate_reference_counts
        plan = GenerationPlan.model_validate({'steps': pending['steps']})
        options = self.generation_options
        if options.get('plan_id') != pending['plan_id']:
            raise ValueError('任务计划已变化，请重新确认')
        steps = []
        kinds = {step.id: step.media_type for step in plan.steps}
        for step in plan.steps:
            parameters, selected = self.generation_parameters(
                step.media_type, {'prompt': step.prompt, 'input_asset_ids': step.input_asset_ids},
                {**options.get(step.media_type, {}), **({'duration': step.duration} if step.duration else {})},
            )
            if step.media_type == 'image' and parameters['n'] != 1:
                raise ValueError('长任务每个图片步骤只生成一张，请将张数改为一张')
            assets = load_chat_assets(step.input_asset_ids, self.user['user_id']) if step.input_asset_ids else []
            image_count = sum(asset['asset_type'] == 'picture' for asset in assets) + sum(kinds[key] == 'image' for key in step.depends_on)
            video_count = sum(asset['asset_type'] == 'video' for asset in assets) + sum(kinds[key] == 'video' for key in step.depends_on)
            validate_reference_counts(selected, image_count, video_count, step.media_type == 'video')
            steps.append({**step.model_dump(exclude_none=True), 'parameters': parameters, 'model_name': selected['name']})
        generation_plan_repo.create_plan(
            pending['plan_id'], self.user['user_id'], self.canvas_id, self.ensure_session(),
            self.ensure_conversation() if self.ensure_conversation else None, steps,
        )
        if self.on_canvas_change:
            await self.on_canvas_change()
        return {'plan_id': pending['plan_id'], 'tasks': session_tasks(self.ensure_session(), self.user['user_id'])}

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
        messages = canvas_repo.get_asset_messages(self.canvas_id, self.user["user_id"])
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
        return await self.discover_and_execute(name, arguments)

    def _selected_generation_options(self, media_type: str, required: tuple[str, ...]) -> dict | None:
        options = dict(self.generation_options)
        if media_type == "video" and "aspect_ratio" not in options and "ratio" in options:
            options["aspect_ratio"] = 'auto' if options["ratio"] == 'adaptive' else options["ratio"]
        if options.get("media_type") != media_type:
            return None
        missing = [key for key in required if options.get(key) is None]
        if missing:
            return None
        return {key: options[key] for key in required}

    def _request_generation_selection(self, media_type: str, arguments: dict) -> dict:
        input_asset_ids = arguments.get("input_asset_ids", [])
        self.pending_generation = {"media_type": media_type, "prompt": arguments.get("prompt", ""), "models": self._models(media_type)}
        if input_asset_ids:
            self.pending_generation.update({
                "tool_name": "img2img" if media_type == "image" else "img2video",
                "input_asset_ids": input_asset_ids,
            })
        return {"selection_required": self.pending_generation}

    def _reference_prompt(self, prompt: str, asset_ids: list[int]) -> str:
        # 界面编号可不连续；生成模型只能看到本次上传的素材及其实际顺序。
        labels = [
            f"第{index}个参考素材对应用户引用的{self.asset_mentions[asset_id]}（资产编号：{asset_id}）"
            for index, asset_id in enumerate(asset_ids, 1) if asset_id in self.asset_mentions
        ]
        return prompt + '\n\n本次上传的参考素材对应关系：\n' + '\n'.join(labels) if labels else prompt

    def _input_assets(self, arguments: dict, media_type: str) -> list[int]:
        asset_ids = arguments.get("input_asset_ids", self.asset_ids)
        if not isinstance(asset_ids, list) or any(type(asset_id) is not int for asset_id in asset_ids):
            raise ValueError("参考资产编号必须是整数列表")
        # 模型给出的子集也按用户本轮引用顺序上传，历史素材继续保留其原有顺序。
        asset_ids = list(dict.fromkeys([
            *(asset_id for asset_id in self.asset_ids if asset_id in asset_ids),
            *asset_ids,
        ]))
        # 即使模型没先调用检索工具，也只接受当前画布实际引用过的编号。
        session_messages = canvas_repo.get_asset_messages(
            self.canvas_id, self.user["user_id"],
        ) if asset_ids else []
        session_asset_ids = {
            asset_id for message in session_messages for asset_id in message["asset_ids"]
        }
        self.allowed_asset_ids.update(session_asset_ids)
        unavailable_ids = sorted(set(asset_ids) - self.allowed_asset_ids)
        if unavailable_ids:
            raise ValueError(
                f"资产 {unavailable_ids} 未关联到当前画布，请先引入这些图片"
            )
        assets = load_chat_assets(asset_ids, self.user["user_id"]) if asset_ids else []
        if media_type == "image" and any(asset["asset_type"] != "picture" for asset in assets):
            raise ValueError("生成图片仅支持参考图片，请移除视频资产")
        return [asset["id"] for asset in assets]
