"""
对话管理 Agent
"""
import json
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from graph.states import ConversationState


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

    async def understand_intent(self, state: ConversationState) -> ConversationState:
        """识别用户意图"""
        if state.get("intent"):
            return state

        messages = state["messages"]
        last_message = messages[-1]["content"] if messages else ""

        # 调用 LLM 识别意图
        system_prompt = f"""你是一个意图识别助手。用户的消息可能是以下意图之一：
{json.dumps(self.intents, ensure_ascii=False, indent=2)}

请分析用户消息，返回 JSON 格式：
{{"intent": "short_drama/batch_image/single_video/image_to_video/unknown"}}

如果无法确定意图，返回 "unknown"。
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": last_message}
            ],
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        intent = result.get("intent")

        if intent and intent in self.intents:
            state["intent"] = intent
            state["current_step"] = "parameter_extraction"
        else:
            state["current_step"] = "intent_clarification"

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

返回 JSON 格式，只包含已明确提到的参数，未提到的不要猜测：
{{"参数名": "参数值", ...}}

如果参数是文件路径，直接返回路径字符串。
如果参数是数值，返回数字类型。
"""

        # 构建对话历史
        conversation = []
        for msg in state["messages"]:
            conversation.append({"role": msg["role"], "content": msg["content"]})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                *conversation
            ],
            response_format={"type": "json_object"}
        )

        extracted = json.loads(response.choices[0].message.content)

        # 更新参数
        if "parameters" not in state:
            state["parameters"] = {}
        state["parameters"].update(extracted)

        # 检查缺失的必填参数
        missing = [p for p in required_params if p not in state["parameters"]]
        state["missing_params"] = missing

        if not missing:
            state["current_step"] = "validation"
        else:
            state["current_step"] = "asking"

        return state

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
                     existing_state: Optional[ConversationState] = None) -> Dict[str, Any]:
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

        # 执行对话流程
        if state["current_step"] == "intent_recognition":
            state = await self.understand_intent(state)

        if state["current_step"] == "intent_clarification":
            reply = "请问你想做什么？\n1. 短剧制作（从剧本到视频）\n2. 批量生图\n3. 单个视频生成\n4. 图生视频"
            state["messages"].append({"role": "agent", "content": reply})
            return {
                "reply": reply,
                "state": state,
                "workflow_ready": False
            }

        if state["current_step"] == "parameter_extraction":
            state = await self.extract_parameters(state)

        if state["current_step"] == "asking":
            # 检查是否有验证错误
            if "_validation_errors" in state["parameters"]:
                errors = state["parameters"]["_validation_errors"]
                reply = "参数验证失败：\n" + "\n".join(f"- {e}" for e in errors)
                del state["parameters"]["_validation_errors"]
            else:
                reply = await self.generate_question(state)

            state["messages"].append({"role": "agent", "content": reply})
            return {
                "reply": reply,
                "state": state,
                "workflow_ready": False
            }

        if state["current_step"] == "validation":
            state = await self.validate_parameters(state)

            if not state["workflow_ready"]:
                # 验证失败，返回错误消息
                return await self.process("", session_id, user_id, state)

        # 参数收集完成
        if state["workflow_ready"]:
            intent_name = self.intents[state["intent"]]["name"]
            reply = f"好的，参数已收集完成。准备为你生成【{intent_name}】工作流..."

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
