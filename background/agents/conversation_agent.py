"""根据对话调用模型查询、图片生成工具。

阅读本文件时，先记住三个位置：

1. ``client.chat.completions.create`` 是发起语言模型请求的入口。
2. ``async for chunk in stream`` 是读取语言模型流式返回的入口。
3. ``tool_executor(name, arguments)`` 是模型要求调用后端工具的入口。

语言模型负责理解用户意图和选择工具；后端工具负责查数据库、校验参数和提交任务。
"""
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from openai import AsyncOpenAI
from graph.states import ConversationState

logger = logging.getLogger(__name__)

DISCOVER_TOOL = {
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
}


class ConversationAgent:
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "gpt-4"):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def process(
        self, message: str, session_id: Optional[str], user_id: int,
        existing_state: Optional[ConversationState] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        tool_executor: Optional[Callable[[str, dict], Awaitable[dict]]] = None,
        tool_discoverer: Optional[Callable[[str], list]] = None,
        executions: Optional[list] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # 这里的 state 是本轮对话的上下文。已有会话会带着数据库历史进入；
        # 新会话则从空消息开始。模型能否理解“2”“openai”“1”等简短回答，
        # 取决于这里是否把前几轮消息一起传给它。
        state = existing_state or {
            "session_id": session_id, "user_id": user_id, "messages": [],
            "intent": None, "parameters": {}, "missing_params": [],
            "workflow_ready": False, "current_step": "conversation",
        }
        # 先把当前用户消息加入上下文，再连同历史消息一起发送给语言模型。
        state["messages"].append({"role": "user", "content": message})
        system_prompt = f"""你是一个可以使用后端能力的创作助手，当前对话模型是 {self.model}。
结合完整历史理解用户的简短回答和选项编号，自然地回应、回答问题；不要无条件展示菜单或按固定表单逐项追问。
首轮只提供了工具发现入口。需要读取或改变后端数据时，先按用户语义调用 discover_tools 寻找相关能力；发现结果会在后续请求中提供，不能猜工具名或假称执行。
只有用户明确要求执行生成、查询、修改等动作时才调用对应工具；普通问题直接回答。工具返回错误时说明错误，不要编造成功结果。
生成、查询工具只能访问当前用户允许的数据。未从工具结果中确认的模型、图片和任务都不能当作真实数据。
历史收集的参数（仅供理解，不能据此假定工具已经执行）：{json.dumps(state.get('parameters', {}), ensure_ascii=False)}
该会话已经提交的真实任务：{json.dumps(executions or [], ensure_ascii=False, default=str)}
"""
        messages = [{"role": "system", "content": system_prompt}] + [
            {"role": "assistant" if msg["role"] == "agent" else msg["role"], "content": msg["content"]}
            for msg in state["messages"]
        ]
        reply_parts = []
        submitted = []
        available_tools = {}
        # 一轮用户消息可能需要多次模型请求：
        # 第一次请求可能要求查询模型，工具返回后再请求一次，最后生成自然语言回复。
        for turn in range(8):
            if on_progress:
                await on_progress("正在结合上下文处理请求" if turn == 0 else "正在根据工具结果继续处理")
            started_at = time.perf_counter()
            request_tools = [DISCOVER_TOOL, *available_tools.values()]
            tool_names = [tool["function"]["name"] for tool in request_tools]
            logger.info(
                "对话模型开始 request_id=%s model=%s session_id=%s round=%s messages=%s provided_tools=%s",
                request_id, self.model, session_id, turn, len(messages), tool_names,
            )
            content = ""
            calls = {}
            try:
                # =====【语言模型调用入口】=====
                # 程序在这里把“系统规则 + 完整历史 + 工具定义”发给语言模型。
                # stream=True 表示模型不会一次性返回完整结果，而是分片返回。
                stream = await self.client.chat.completions.create(
                    model=self.model, messages=messages, tools=request_tools,
                    parallel_tool_calls=False, stream=True,
                )
                try:
                    # =====【语言模型返回读取位置】=====
                    # 每个 chunk 都是模型返回的一小段内容。
                    # chunk.choices[0].delta.content 是普通文字；
                    # delta.tool_calls 是模型要求调用工具的内容。
                    async for chunk in stream:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        # 模型正在输出给用户看的文字，例如“我先查询可用模型”。
                        if delta.content:
                            content += delta.content
                            reply_parts.append(delta.content)
                            if on_delta:
                                await on_delta(delta.content)
                        # 模型也可能不输出文字，而是输出工具调用。
                        # 工具调用参数可能被拆成多个 chunk，所以先按 index 拼接起来。
                        for call in delta.tool_calls or []:
                            item = calls.setdefault(call.index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            if call.id:
                                item["id"] = call.id
                            if call.function:
                                item["function"]["name"] += call.function.name or ""
                                item["function"]["arguments"] += call.function.arguments or ""
                finally:
                    await stream.close()
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
                request_id, session_id, turn, len(calls),
                round((time.perf_counter() - started_at) * 1000),
                json.dumps(content, ensure_ascii=False),
            )
            if not calls:
                break
            # 把模型刚才的工具调用原样放回上下文，下一次模型请求才能知道自己调用过什么。
            messages.append({"role": "assistant", "content": content or None, "tool_calls": list(calls.values())})
            for call in calls.values():
                name = call["function"]["name"]
                logger.info(
                    "对话模型请求调用工具 request_id=%s session_id=%s round=%s tool=%s arguments=%s",
                    request_id, session_id, turn, name, call["function"]["arguments"],
                )
                if on_progress:
                    await on_progress("正在查找适用工具" if name == "discover_tools" else f"正在执行工具：{name}")
                try:
                    arguments = json.loads(call["function"]["arguments"])
                    if name == "discover_tools":
                        if not tool_discoverer:
                            raise ValueError("当前未配置工具发现目录")
                        found_tools = tool_discoverer(arguments["query"])
                        for found in found_tools:
                            schema = {"type": found["type"], "function": found["function"]}
                            available_tools[found["function"]["name"]] = schema
                        result = {
                            "available_tools": [
                                {"name": found["function"]["name"], "description": found["function"]["description"]}
                                for found in found_tools
                            ]
                        }
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
                if name in ("txt2img", "txt2video") and result.get("task_id"):
                    submitted.append(result)
                    if name == "txt2img":
                        state["intent"] = "batch_image"
                        state["parameters"] = result["parameters"]
                    else:
                        state["intent"] = "text_to_video"
                        state["parameters"] = result["parameters"]
                # 工具结果也要放回上下文，让语言模型根据真实数据库/接口结果继续回答。
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False, default=str)})
        else:
            text = "本次工具调用次数已达上限，请稍后继续。"
            reply_parts.append(text)
            if on_delta:
                await on_delta(text)

        # 这里是本轮模型最终给用户看的文字。工具调用本身不是回复，
        # 只有模型在工具结果之后生成的文字才会进入 reply。
        reply = "".join(reply_parts).strip()
        if not reply:
            reply = "生成任务已提交，请查看下方进度。" if submitted else "本次未提交生成任务，请补充你的需求。"
            if on_delta:
                await on_delta(reply)
        state["messages"].append({"role": "agent", "content": reply})
        state["workflow_ready"] = bool(submitted)
        return {"reply": reply, "state": state, "workflow_ready": bool(submitted), "tasks": submitted}
