"""
对话管理 Agent
"""
import json
import logging
import time
from typing import Dict, Any, List, Optional, Callable, Awaitable
from openai import AsyncOpenAI
from graph.states import ConversationState

logger = logging.getLogger(__name__)


class ConversationAgent:
    """对话管理 Agent，负责多轮对话收集参数"""

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "gpt-4"):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

        # 意图定义
        self.intents = {
            "short_drama": {
                "name": "短剧制作",
                "required_params": ["script_path_or_content", "shot_count", "video_duration", "model"],
                "optional_params": ["aspect_ratio", "resolution", "style"]
            },
            "batch_image": {
                "name": "批量生图",
                "required_params": ["prompts", "count", "model"],
                "optional_params": ["aspect_ratio", "style", "reference_image"]
            },
            "single_video": {
                "name": "单个视频生成",
                "required_params": ["prompt", "duration", "model"],
                "optional_params": ["resolution", "ratio", "reference_image"]
            },
            "image_to_video": {
                "name": "图生视频",
                "required_params": ["image_path_or_id", "duration", "model"],
                "optional_params": ["prompt", "resolution"]
            }
        }

        # 参数说明
        self.param_descriptions = {
            "script_path_or_content": "剧本文件路径或文本内容",
            "shot_count": "需要生成的分镜数量（如 10）",
            "video_duration": "每个视频的时长（秒，如 5）",
            "model": "使用的模型（ark/openai/gemini）",
            "prompts": "提示词列表或单个提示词",
            "count": "生成数量",
            "prompt": "生成提示词",
            "duration": "视频时长（秒）",
            "aspect_ratio": "宽高比（如 16:9, 9:16, 1:1）",
            "resolution": "分辨率（如 1080p, 720p）",
            "style": "风格描述",
            "reference_image": "参考图片路径或 ID",
            "image_path_or_id": "图片文件路径或资产 ID",
            "ratio": "视频比例"
        }

    def _model_messages(self, state: ConversationState) -> List[Dict[str, str]]:
        """保留对话顺序，并将数据库角色转换为模型接口支持的角色。"""
        return [
            {"role": "assistant" if msg["role"] == "agent" else msg["role"],
             "content": msg["content"]}
            for msg in state["messages"]
        ]

    async def understand_intent(self, state: ConversationState) -> ConversationState:
        """识别用户意图"""
        if state.get("intent"):
            return state

        # 调用 LLM 识别意图
        system_prompt = f"""你是一个意图识别助手。用户的消息可能是以下意图之一：
{json.dumps(self.intents, ensure_ascii=False, indent=2)}

请结合完整对话历史理解用户最新消息，返回 JSON 格式：
{{"intent": "short_drama/batch_image/single_video/image_to_video/unknown", "reply": "仅在 intent 为 unknown 时，对用户最新问题给出自然、简短的直接回应"}}

如果用户回答的是上一轮助手列出的选项编号，应根据上一轮选项判断意图。
如果用户在询问与你当前模型身份有关的问题，先回答当前模型名：{self.model}；随后自然地提供任务入口，并列出选项：1. 短剧制作，2. 批量生图，3. 单个视频生成，4. 图生视频，方便用户直接回复编号。其他闲聊或不明确请求先自然回应，再简短询问用户要完成什么。
如果无法确定意图，返回 "unknown"。
"""

        response = await self._create_completion("intent_recognition", [
            {"role": "system", "content": system_prompt},
            *self._model_messages(state)
        ])

        result = json.loads(response.choices[0].message.content)
        intent = result.get("intent")

        if intent and intent in self.intents:
            state["intent"] = intent
            state["current_step"] = "parameter_extraction"
        else:
            state["current_step"] = "intent_clarification"
            state["reply"] = result.get("reply", "")

        return state

    async def extract_parameters(self, state: ConversationState) -> ConversationState:
        """从对话历史中提取参数"""
        intent = state.get("intent")
        if not intent:
            return state

        intent_config = self.intents[intent]
        required_params = intent_config["required_params"]
        optional_params = intent_config["optional_params"]
        all_params = required_params + optional_params

        # 构建提取提示词
        param_schema = {param: self.param_descriptions.get(param, "") for param in all_params}

        system_prompt = f"""你是一个参数提取助手。从对话历史中提取以下参数：
{json.dumps(param_schema, ensure_ascii=False, indent=2)}

必填参数：{required_params}
可选参数：{optional_params}

当前已收集的参数：{json.dumps(state.get("parameters", {}), ensure_ascii=False)}
结合助手上一轮的问题理解简短回答；用户明确修改参数时，以最新回答为准。
助手给出的示例、推荐值和任务选项编号不代表用户已选择的参数。

返回 JSON 格式，parameters 只包含已明确提到或根据最新回答修正的参数，不要猜测：
{{"parameters": {{"参数名": "参数值"}}, "reply": "自然简短地回应用户，并只追问下一个最重要的缺失信息；如果已经齐全则简短确认"}}

如果参数是文件路径，直接返回路径字符串。
如果参数是数值，返回数字类型。
"""

        # 构建对话历史
        conversation = self._model_messages(state)

        response = await self._create_completion("parameter_extraction", [
            {"role": "system", "content": system_prompt},
            *conversation
        ])

        extracted = json.loads(response.choices[0].message.content)
        if "parameters" in extracted:
            state["reply"] = extracted.get("reply", "")
            extracted = extracted["parameters"]

        # 更新参数
        if "parameters" not in state:
            state["parameters"] = {}
        state["parameters"].update(extracted)

        # 检查缺失的必填参数
        missing = [p for p in required_params if p not in state["parameters"]]
        state["missing_params"] = missing
        logger.info(
            "工作流参数整理完成 intent=%s collected_keys=%s missing_required=%s",
            intent, sorted(state["parameters"].keys()), missing
        )

        if not missing:
            state["current_step"] = "validation"
        else:
            state["current_step"] = "asking"

        return state

    async def _create_completion(self, stage: str, messages: List[Dict[str, str]]):
        started_at = time.perf_counter()
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"}
            )
        except Exception:
            logger.exception("工作流模型调用失败 stage=%s model=%s", stage, self.model)
            raise
        elapsed_ms = round((time.perf_counter() - started_at) * 1000)
        logger.info("工作流模型调用完成 stage=%s model=%s elapsed_ms=%d", stage, self.model, elapsed_ms)
        return response

    async def generate_question(self, state: ConversationState) -> str:
        """生成追问问题"""
        missing_params = state.get("missing_params", [])
        if not missing_params:
            return ""

        # 询问第一个缺失参数
        next_param = missing_params[0]
        param_desc = self.param_descriptions.get(next_param, next_param)

        intent = state.get("intent")
        intent_name = self.intents[intent]["name"] if intent else "任务"

        # 根据参数类型生成合适的问题
        questions = {
            "script_path_or_content": "请提供剧本文件路径，或者直接粘贴剧本内容",
            "shot_count": "需要生成多少个分镜？",
            "video_duration": "每个视频片段的时长是多少秒？（推荐 5-10 秒）",
            "model": "使用哪个模型？\n- ark：质量高但较慢\n- openai：平衡质量和速度\n- gemini：速度快成本低",
            "prompts": "请提供生成提示词（多个提示词用换行分隔）",
            "count": "需要生成多少张图片？",
            "prompt": "请描述你想生成的内容",
            "duration": "视频时长是多少秒？",
            "image_path_or_id": "请提供图片文件路径或资产 ID",
        }

        question = questions.get(next_param, f"请提供{param_desc}")

        return question

    async def validate_parameters(self, state: ConversationState) -> ConversationState:
        """验证参数合理性"""
        parameters = state.get("parameters", {})
        errors = []

        # 验证 shot_count
        if "shot_count" in parameters:
            try:
                count = int(parameters["shot_count"])
                if count <= 0 or count > 100:
                    errors.append("分镜数量应在 1-100 之间")
            except ValueError:
                errors.append("分镜数量应为整数")

        # 验证 video_duration
        if "video_duration" in parameters:
            try:
                duration = float(parameters["video_duration"])
                if duration <= 0 or duration > 60:
                    errors.append("视频时长应在 0-60 秒之间")
            except ValueError:
                errors.append("视频时长应为数字")

        # 验证 model
        if "model" in parameters:
            valid_models = ["ark", "openai", "gemini", "seedance"]
            if parameters["model"] not in valid_models:
                errors.append(f"模型应为：{', '.join(valid_models)}")

        if errors:
            state["current_step"] = "asking"
            state["missing_params"] = ["validation_error"]
            state["parameters"]["_validation_errors"] = errors
        else:
            state["workflow_ready"] = True
            state["current_step"] = "ready"

        return state

    async def process(self, message: str, session_id: str, user_id: int,
                     existing_state: Optional[ConversationState] = None,
                     on_progress: Optional[Callable[[str], Awaitable[None]]] = None) -> Dict[str, Any]:
        """处理用户消息"""

        # 初始化或恢复状态
        if existing_state:
            state = existing_state
        else:
            state: ConversationState = {
                "session_id": session_id,
                "user_id": user_id,
                "messages": [],
                "intent": None,
                "parameters": {},
                "missing_params": [],
                "workflow_ready": False,
                "current_step": "intent_recognition"
            }

        # 添加用户消息
        state["messages"].append({"role": "user", "content": message})
        # 每条新消息都重新提取、验证，不能沿用上轮的追问或就绪标记。
        state["current_step"] = "parameter_extraction" if state.get("intent") else "intent_recognition"
        state["workflow_ready"] = False

        # 执行对话流程
        if state["current_step"] == "intent_recognition":
            if on_progress:
                await on_progress("正在结合对话上下文识别你的请求")
            state = await self.understand_intent(state)

        if state["current_step"] == "intent_clarification":
            reply = state.get("reply") or "你想完成哪类任务？例如短剧制作、批量生图、视频生成或图生视频。"
            state["messages"].append({"role": "agent", "content": reply})
            return {
                "reply": reply,
                "state": state,
                "workflow_ready": False
            }

        if state["current_step"] == "parameter_extraction":
            if on_progress:
                await on_progress("正在结合历史消息整理已提供的信息")
            state = await self.extract_parameters(state)

        if state["current_step"] == "validation":
            if on_progress:
                await on_progress("正在检查必填参数和取值")
            state = await self.validate_parameters(state)

        if state["current_step"] == "asking":
            # 检查是否有验证错误
            if "_validation_errors" in state["parameters"]:
                errors = state["parameters"]["_validation_errors"]
                reply = "参数验证失败：\n" + "\n".join(f"- {e}" for e in errors)
                del state["parameters"]["_validation_errors"]
            else:
                reply = state.get("reply") or await self.generate_question(state)

            state["messages"].append({"role": "agent", "content": reply})
            return {
                "reply": reply,
                "state": state,
                "workflow_ready": False
            }

        # 参数收集完成
        if state["workflow_ready"]:
            intent_name = self.intents[state["intent"]]["name"]
            reply = state.get("reply") or f"好的，参数已收集完成。准备为你生成【{intent_name}】工作流..."

            state["messages"].append({"role": "agent", "content": reply})

            return {
                "reply": reply,
                "state": state,
                "workflow_ready": True,
                "intent": state["intent"],
                "parameters": state["parameters"]
            }

        return {
            "reply": "继续...",
            "state": state,
            "workflow_ready": False
        }
