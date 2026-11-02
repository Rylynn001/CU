"""对话助手：process 是主流程，下面的方法分别处理上下文、模型请求和工具调用。"""
import json
import logging
import time
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx
from openai import AsyncOpenAI
from .graph.states import ConversationState
from .services.workflow_tool_definitions import WorkflowTool

logger = logging.getLogger(__name__)


class ConversationPrompt(str, Enum):
    SYSTEM = """你是一个可以使用后端能力的创作助手，当前对话模型是 {model}。
结合完整历史理解用户的简短回答和选项编号，自然地回应、回答问题；不要无条件展示菜单或按固定表单逐项追问。

**工具使用规则**：
首轮只提供了工具发现入口。当用户需要以下任何能力时，先调用 discover_tools 寻找相关工具：
1. 数据操作：读取或改变后端数据（查询模型、生成图片/视频、查询历史等）
2. 专业内容生成：需要遵循特定平台规范的提示词生成（如 Seedance/即梦视频提示词、图生视频提示词等）
3. 复杂格式转换：需要专业知识的内容转换（如分镜脚本、运镜描述等）

发现结果会在后续请求中提供，不能猜工具名或假称执行。
只有用户明确要求执行生成、查询、修改等动作，或请求专业格式内容时才调用对应工具；普通问题直接回答。
工具返回错误时说明错误，不要编造成功结果。

**生成工作流**：
- 当生成视频提示词后，主动询问用户是否需要实际生成图片或视频
- 图片生成流程：list_image_models → 确认模型 → txt2img
- 视频生成流程：list_video_models → 确认模型 → txt2video
- 不要假设用户已有模型选择，必须先查询模型列表

生成、查询工具只能访问当前用户允许的数据。未从工具结果中确认的模型、图片和任务都不能当作真实数据。
用户要求实际生成图片或视频时，调用 txt2img 或 txt2video 并传入内容描述，后端会展示参数选择表单。
用户提供的参考图片和视频画面会随消息发送，资产编号由后端标注。根据这些实际内容理解用户需求，不要声称未收到图片。
需要参考图片生成图片时使用 img2img；需要参考图片或视频生成视频时使用 img2video，并传入 input_asset_ids。
需要复用本会话之前消息中引入的图片时，先调用 search_session_reference_assets，按消息内容关键词查找并使用匹配结果中的资产编号。不能跨会话搜索，也不能猜编号；找不到时说明并让用户在当前会话重新引入。
如果用户只是确认上一轮提示词，但该提示词要求参考图片，也先搜索本会话之前消息中已引入的图片，再提交参考资产生成任务。
只能使用当前会话中用户引入或 search_session_reference_assets 返回的资产编号；没有参考资产时使用 txt2img 或 txt2video。视频画面不包含音频，不得推测声音内容。
不要在文字回复中罗列编号要求用户复制选项，不得猜测模型、比例、质量、数量或时长。参数以用户在页面选择的值为准。
历史收集的参数（仅供理解，不能据此假定工具已经执行）：
{parameters}
该会话已经提交的真实任务：
{executions}"""

class ConversationAgent:
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "gpt-4"):
        self.client = AsyncOpenAI(
            api_key=api_key, base_url=base_url,
            timeout=httpx.Timeout(30.0, connect=30.0),
        )
        self.model = model

    async def process(
        self, message: str, session_id: Optional[int], user_id: int,
        existing_state: Optional[ConversationState] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        tool_executor: Optional[Callable[[str, dict], Awaitable[dict]]] = None,
        tool_discoverer: Optional[Callable[[str], list]] = None,
        executions: Optional[list] = None,
        request_id: Optional[str] = None,
        user_content: Optional[list | str] = None,
    ) -> Dict[str, Any]:
        """主流程：准备上下文 → 请求模型 → 执行工具 → 将工具结果交回模型。"""
        state = existing_state or {
            "session_id": session_id, "user_id": user_id, "messages": [],
            "intent": None, "parameters": {}, "missing_params": [],
            "workflow_ready": False, "current_step": "conversation",
        }
        state["messages"].append({"role": "user", "content": user_content if user_content is not None else message})
        messages = self._build_model_messages(state, executions)
        reply_parts = []
        submitted = []
        available_tools = {}

        # 一条用户消息最多请求模型 8 轮。工具执行后，需要再请模型读取结果并继续回答。
        for turn in range(8):
            if on_progress:
                stage = "正在结合上下文处理请求" if turn == 0 else "正在根据工具结果继续处理"
                await on_progress(stage)
            request_tools = [WorkflowTool.DISCOVER_TOOLS.value, *available_tools.values()]
            tool_choice = self._choose_tool(message, turn, request_id)
            started_at = time.perf_counter()
            logger.info(
                "对话模型开始 request_id=%s model=%s session_id=%s round=%s messages=%s provided_tools=%s",
                request_id, self.model, session_id, turn, len(messages),
                [tool["function"]["name"] for tool in request_tools],
            )

            # 1. 请求语言模型。普通文字立即发送；工具调用等参数拼完整后再执行。
            try:
                content, tool_calls = await self._request_model(
                    messages, request_tools, tool_choice, reply_parts, on_delta
                )
            except Exception:
                logger.exception("对话模型失败 request_id=%s session_id=%s round=%s", request_id, session_id, turn)
                if not submitted:
                    raise
                text = "生成任务已提交，请查看任务进度。回复服务暂时不可用，不影响已提交的任务。"
                reply_parts.append(text)
                if on_delta:
                    await on_delta(text)
                break
            logger.info(
                "对话模型完成 request_id=%s session_id=%s round=%s tool_count=%s elapsed_ms=%s response=%s",
                request_id, session_id, turn, len(tool_calls),
                round((time.perf_counter() - started_at) * 1000), json.dumps(content, ensure_ascii=False),
            )

            # 2. 没有工具调用，说明模型本轮只回复文字，聊天可以结束。
            if not tool_calls:
                break
            messages.append({"role": "assistant", "content": content or None, "tool_calls": tool_calls})

            # 3. 执行模型要求的工具，把真实结果加入上下文，供下一轮模型读取。
            selection_requested = False
            for call in tool_calls:
                name = call["function"]["name"]
                if on_progress:
                    stage = "正在查找适用工具" if name == "discover_tools" else f"正在执行工具：{name}"
                    await on_progress(stage)
                result = await self._execute_tool_call(
                    call, available_tools, tool_executor, tool_discoverer, request_id, session_id, turn
                )
                if name in ("txt2img", "txt2video", "img2img", "img2video") and result.get("task_id"):
                    submitted.append(result)
                    state["intent"] = "batch_image" if name in ("txt2img", "img2img") else "text_to_video"
                    state["parameters"] = result["parameters"]
                messages.append({
                    "role": "tool", "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
                if result.get("selection_required"):
                    selection_requested = True
                    text = "请在弹出的选择框中选择生成模型和参数，确认后开始生成。"
                    reply_parts.append(text)
                    if on_delta:
                        await on_delta(text)
                    break
            if selection_requested:
                break
        else:
            text = "本次工具调用次数已达上限，请稍后继续。"
            reply_parts.append(text)
            if on_delta:
                await on_delta(text)

        # 4. 汇总各轮已经发给前端的文字。任务已提交不代表图片或视频已生成完成。
        reply = "".join(reply_parts).strip()
        if not reply:
            reply = "生成任务已提交，请查看下方进度。" if submitted else "本次未提交生成任务，请补充你的需求。"
            if on_delta:
                await on_delta(reply)
        state["messages"].append({"role": "agent", "content": reply})
        state["workflow_ready"] = bool(submitted)
        return {"reply": reply, "state": state, "workflow_ready": bool(submitted), "tasks": submitted}

    def _build_model_messages(self, state: ConversationState, executions: Optional[list]) -> list:
        """把系统规则、历史消息和本次用户消息组合成模型上下文。"""
        system_prompt = ConversationPrompt.SYSTEM.value.format(
            model=self.model,
            parameters=json.dumps(state.get("parameters", {}), ensure_ascii=False, indent=2, default=str),
            executions=json.dumps(executions or [], ensure_ascii=False, indent=2, default=str),
        )
        messages = [{"role": "system", "content": system_prompt}] + [
            {"role": "assistant" if msg["role"] == "agent" else msg["role"], "content": msg["content"]}
            for msg in state["messages"]
        ]
        return messages

    def _choose_tool(self, message: str, turn: int, request_id: Optional[str]):
        """首轮命中专业内容关键词时，强制发现工具；其余情况由模型选择。"""
        if turn != 0:
            return None
        content_keywords = [
            "seedance", "即梦", "视频提示词", "视频脚本",
            "分镜", "运镜", "剪辑节奏", "时间戳",
        ]
        matched_keywords = [keyword for keyword in content_keywords if keyword in message.lower()]
        if not matched_keywords:
            return None
        logger.info(
            "检测到专业内容关键词，强制调用 discover_tools request_id=%s keywords=%s",
            request_id, matched_keywords,
        )
        return {"type": "function", "function": {"name": "discover_tools"}}

    async def _request_model(self, messages, tools, tool_choice, reply_parts, on_delta):
        """读取一轮模型响应：即时发送文字，按索引拼接被分片传输的工具名称和参数。"""
        stream = await self.client.chat.completions.create(
            model=self.model, messages=messages, tools=tools,
            tool_choice=tool_choice, parallel_tool_calls=False, stream=True,
        )
        content = ""
        calls = {}
        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    content += delta.content
                    # 立即保留已发送文字，即使本轮流式读取中途失败也不会丢失。
                    reply_parts.append(delta.content)
                    if on_delta:
                        await on_delta(delta.content)
                for fragment in delta.tool_calls or []:
                    call = calls.setdefault(fragment.index, {
                        "id": "", "type": "function",
                        "function": {"name": "", "arguments": ""},
                    })
                    if fragment.id:
                        call["id"] = fragment.id
                    if fragment.function:
                        call["function"]["name"] += fragment.function.name or ""
                        call["function"]["arguments"] += fragment.function.arguments or ""
        finally:
            await stream.close()
        return content, list(calls.values())

    async def _execute_tool_call(
        self, call, available_tools, tool_executor, tool_discoverer, request_id, session_id, turn
    ) -> dict:
        """发现工具或执行已发现的工具；失败结果也交回模型，禁止假报执行成功。"""
        name = call["function"]["name"]
        logger.info(
            "对话模型请求调用工具 request_id=%s session_id=%s round=%s tool=%s arguments=%s",
            request_id, session_id, turn, name, call["function"]["arguments"],
        )
        try:
            arguments = json.loads(call["function"]["arguments"])
            if name == "discover_tools":
                result = self._discover_tools(arguments["query"], available_tools, tool_discoverer)
            else:
                if name not in available_tools:
                    raise ValueError("工具尚未通过发现步骤加载")
                if not tool_executor:
                    raise ValueError("当前未配置工具执行器")
                result = await tool_executor(name, arguments)
        except Exception as error:
            logger.exception("对话工具失败 request_id=%s session_id=%s tool=%s", request_id, session_id, name)
            result = {"error": getattr(error, "detail", None) or str(error)}
        logger.info(
            "对话工具返回 request_id=%s session_id=%s tool=%s result=%s",
            request_id, session_id, name, json.dumps(result, ensure_ascii=False, default=str),
        )
        return result

    def _discover_tools(self, query: str, available_tools: dict, tool_discoverer) -> dict:
        """用模型给出的查询词搜索目录，并把找到的工具定义提供给下一轮模型。"""
        if not tool_discoverer:
            raise ValueError("当前未配置工具发现目录")
        found_tools = tool_discoverer(query)
        for tool in found_tools:
            name = tool["function"]["name"]
            available_tools[name] = {"type": tool["type"], "function": tool["function"]}
        return {
            "available_tools": [
                {"name": tool["function"]["name"], "description": tool["function"]["description"]}
                for tool in found_tools
            ]
        }
