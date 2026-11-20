"""
工作流 API
"""
import asyncio
import json
import logging
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any, List

from api.auth import get_current_user
from agents.graph.workflow import create_conversation_workflow
from openai import AsyncOpenAI
from repositories.workflow_repo import WorkflowRepository
from repositories import canvas_repo
from repositories.generation_repo import get_language_model_info
from config import get_provider_config_by_rfid
from agents.graph.states import ConversationState
from agents.services.workflow_tools import WorkflowTools, session_tasks
from agents.services.chat_assets import load_chat_assets, build_asset_content, asset_previews, node_reference_images
from agents.services.canvas_tasks import refresh_tasks, apply_tasks
from agents.skill_agent import SkillManager
from agents.graph.utils.usage import read_model_usage
from agents.graph.utils.prompt_validation import validate_final_prompt

router = APIRouter(prefix="/workflow", tags=["workflow"])
logger = logging.getLogger(__name__)


def _get_llm_client(model_id: int):
    """按模型编号创建 AsyncOpenAI 客户端，返回 (client, model_name)。"""
    model_info = get_language_model_info(model_id)
    if not model_info:
        raise HTTPException(status_code=404, detail=f"未找到语言模型配置（id={model_id}）")
    provider_config = get_provider_config_by_rfid(model_info['rfid'])
    if not provider_config:
        raise HTTPException(status_code=500, detail="未找到语言模型的服务配置")
    client = AsyncOpenAI(api_key=provider_config['api_key'], base_url=provider_config['base_url'])
    return client, model_info['name'], model_info.get('context_window')


_GRAPH_NODE_PROGRESS = {
    "intent": "正在分析你的请求…",
    "prompt_enhance": "正在优化提示词…",
    "direct_execute": "准备生成参数…",
    "execute_tool": "正在执行生成任务…",
}


async def _run_conversation_graph(
    request: 'ChatRequest',
    workflow_tools,
    existing_state: Optional[dict],
    user_content: str | list,
    request_id: str,
    on_progress=None,
    on_delta=None,
    on_event=None,
    skill_instruction: str = '',
) -> dict:
    """运行一次普通对话图。

    输入：历史消息、当前用户消息、素材和可选技能规则。
    输出：文字回复、待确认的 generation_request，或已提交的 tasks。
    注意：这里最多负责提交任务，不等待图片/视频生成完成。
    """
    llm_client, model_name, context_window = _get_llm_client(request.model_id)
    context_usage = None

    async def record_event(event, data):
        nonlocal context_usage
        if event == 'usage':
            context_usage = {**data, 'max_tokens': context_window}
            data = context_usage
        if on_event:
            await on_event(event, data)

    graph = create_conversation_workflow(workflow_tools=workflow_tools, llm_client=llm_client, model_name=model_name, on_event=record_event, skill_instruction=skill_instruction)

    messages = list((existing_state or {}).get("messages", []))
    if skill_instruction:
        messages.insert(0, {'role': 'system', 'content': (
            '用户为本轮对话主动选择了以下技能。按技能要求回答或编写生成提示词；'
            '是否实际生成仍以用户请求为准，不要擅自执行生成或外部命令。\n\n' + skill_instruction
        )})
    messages.append({"role": "user", "content": user_content})  # LangChain 标准角色

    initial_state = {
        "messages": messages,
        "enable_prompt_optimization": True,
        "intent": None,
        "generation_request": None,
        # 追问阶段保存整份计划草稿，下一轮继续当前步骤，不从头生成。
        "generation_draft": (existing_state or {}).get("generation_draft"),
        "asset_ids": workflow_tools.asset_ids,
        "current_tool": None,
        "tool_result": None,
        "loop_count": 0,
        "is_complete": False,
    }

    config = {"configurable": {"thread_id": f"req_{request_id}"}}
    final_state: dict = dict(initial_state)

    # values 模式逐节点返回完整状态；这里用它推送进度，并在图结束后读取 tool_result。
    async for state in graph.astream(initial_state, config=config, stream_mode="values"):
        if isinstance(state, dict) and on_progress:
            if state.get("intent") and not final_state.get("intent"):
                await on_progress(_GRAPH_NODE_PROGRESS["intent"])
            elif state.get("generation_request") and not final_state.get("generation_request"):
                await on_progress(_GRAPH_NODE_PROGRESS["direct_execute"])
            elif state.get("tool_result") and not final_state.get("tool_result"):
                await on_progress(_GRAPH_NODE_PROGRESS["execute_tool"])
        if isinstance(state, dict):
            final_state = state

    intent = final_state.get("intent")
    tool_result = final_state.get("tool_result") or {}

    logger.info("图执行结束 request_id=%s intent=%s result_keys=%s", request_id, intent, list(tool_result))

    tasks: list = []
    workflow_ready = False
    reply = None

    if isinstance(tool_result, dict):
        if tool_result.get("error"):
            raise HTTPException(status_code=502, detail=str(tool_result["error"]))
        if tool_result.get("reply"):
            # 对话结果
            reply = tool_result["reply"]
        elif tool_result.get("task_id"):
            tasks = [tool_result]
            workflow_ready = True
            reply = "生成任务已提交，请查看下方进度。"
        elif tool_result.get("selection_required"):
            workflow_tools.pending_generation = tool_result["selection_required"]
            reply = "请在弹出的选择框中补全生成参数。"

    if not isinstance(reply, str) or not reply.strip():
        raise HTTPException(status_code=502, detail="本次处理未返回有效结果，请重试")

    if on_delta:
        await on_delta(reply)

    return {
        "reply": reply,
        "state": {"intent": intent},
        "workflow_ready": workflow_ready,
        "tasks": tasks,
        # 首次生成请求可能在提示词优化时暂停；把草稿交给 API 层落库。
        "generation_draft": final_state.get("generation_draft"),
        "context_usage": context_usage,
    }


class ChatRequest(BaseModel):
    """聊天接口的单次请求。

    普通请求先理解需求，可能返回 generation_request 等待参数；
    前端确认后再次请求，generation_options 才会携带已确认参数并提交任务。
    """
    model_config = ConfigDict(protected_namespaces=())

    message: str = Field(description="用户本轮输入的自然语言请求")
    model_id: int = Field(description="负责理解请求和优化提示词的对话模型编号")
    canvas_id: int = Field(gt=0, description="当前画布编号，用于保存节点、会话和任务")
    session_id: Optional[int] = Field(default=None, description="已有工作流会话编号；为空表示新会话")
    generation_options: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "用户在生成参数面板确认后的参数。为空表示先让模型理解请求；"
            "非空表示执行第二阶段，提交模型、比例、质量、分辨率、时长等参数。"
        ),
    )
    asset_ids: List[int] = Field(default_factory=list, max_length=10, description="本轮引用的图片或视频资产编号")
    asset_mentions: Dict[int, str] = Field(default_factory=dict, max_length=10, description="资产编号到 @图片N/@视频N 的映射")
    skill_id: Optional[str] = Field(default=None, max_length=100, description="本轮主动选择的提示词技能编号")
    prompt_optimization: bool = Field(
        default=False,
        description="是否仅优化画布节点提示词；为 true 时只返回文字，不提交图片或视频任务",
    )
    optimization_node_id: Optional[str] = Field(default=None, min_length=1, max_length=100, description="提示词优化的画布节点编号，用于服务端读取上游参考图片")


class ChatResponse(BaseModel):
    reply: str
    optimized_prompt: Optional[str] = None
    session_id: int
    user_conversation_id: Optional[int] = None
    agent_conversation_id: Optional[int] = None
    intent: Optional[str] = None
    workflow_ready: bool
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    generation_request: Optional[Dict[str, Any]] = None
    context_usage: Optional[Dict[str, Any]] = None


@router.get('/skills')
async def list_chat_skills(current_user: dict = Depends(get_current_user)):
    """按需扫描目录，刷新即可发现新增、修改或删除的技能。"""
    skills = await asyncio.to_thread(lambda: SkillManager().list_skills())
    return [{key: skill[key] for key in ('id', 'name', 'description')} for skill in skills]


def _apply_generation_edits(pending: dict, options: dict) -> dict:
    """只允许调整提示词，任务依赖、素材编号等仍使用服务端保存的计划。"""
    def prompt_text(value, original):
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(status_code=400, detail='提示词不能为空')
        # 用户只编辑创作描述；既有素材编号映射由服务端保留。
        marker = '\n\n本次上传的参考素材对应关系：\n'
        _, separator, note = original.partition(marker)
        text = value.partition(marker)[0].strip()
        if not text:
            raise HTTPException(status_code=400, detail='提示词不能为空')
        # 面板允许编辑提示词，确认入口同样拒绝明显的反问，防止绕过首次优化的校验。
        try:
            text = validate_final_prompt(text)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return text + separator + note

    if pending['media_type'] == 'plan' and 'step_prompts' in options:
        prompts = options['step_prompts']
        if not isinstance(prompts, dict) or set(prompts) != {step['id'] for step in pending['steps']}:
            raise HTTPException(status_code=400, detail='任务步骤已变化，请重新确认')
        return {**pending, 'steps': [{**step, 'prompt': prompt_text(prompts[step['id']], step['prompt'])} for step in pending['steps']]}
    if pending['media_type'] != 'plan' and 'prompt' in options:
        return {**pending, 'prompt': prompt_text(options['prompt'], pending['prompt'])}
    return pending


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """HTTP 总入口：完成请求校验后建立 SSE，实际业务由 _process_chat 执行。"""
    return StreamingResponse(
        _stream_chat_events(request, current_user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_chat_events(request: ChatRequest, current_user: dict):
    """SSE 外壳：转发 progress/trace/delta，最后发送 done 或 error。"""
    event_queue = asyncio.Queue()

    async def report_progress(message: str):
        await event_queue.put(("progress", {"message": message}))

    async def report_delta(text: str):
        if isinstance(text, str) and text:
            await event_queue.put(("delta", {"text": text}))

    async def report_event(event: str, data: dict):
        await event_queue.put((event, data))

    # 创建任务只是安排执行；当前协程让出执行权后，聊天业务才有机会运行。
    chat_task = asyncio.create_task(
        _process_chat(request, current_user, report_progress, report_delta, report_event)
    )
    try:
        yield _encode_sse("progress", {"message": "正在准备对话上下文"})

        # 聊天结束后仍要发完队列中的文字，再发送最终结果。
        while not chat_task.done() or not event_queue.empty():
            event = await _wait_for_chat_event(event_queue, chat_task)
            if event is not None:
                event_name, data = event
                yield _encode_sse(event_name, data)
            elif not chat_task.done():
                yield ": keep-alive\n\n"

        result = chat_task.result()
        yield _encode_sse("done", result.model_dump())
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.exception("工作流对话流式请求失败 session_id=%s", request.session_id or "new")
        detail = getattr(error, "detail", None) or str(error) or "对话请求失败"
        if "overloaded" in str(detail).lower():
            detail = "上游对话模型服务当前过载，请稍后重试。"
        yield _encode_sse("error", {"message": detail})
    finally:
        # 浏览器断开或停止读取时，回收本次聊天任务。
        if not chat_task.done():
            chat_task.cancel()
        await asyncio.gather(chat_task, return_exceptions=True)


async def _wait_for_chat_event(event_queue: asyncio.Queue, chat_task: asyncio.Task):
    """等待下一条消息或聊天结束；15 秒无消息则返回 None，让发送方发心跳。"""
    # 获得消息是不是为空？
    if not event_queue.empty():
        return event_queue.get_nowait()
    # 如果消息空的话就再创建一个task去获取队列，等待下一条消息
    next_event_task = asyncio.create_task(event_queue.get())
    #然后同时等待
    try:
        completed, _ = await asyncio.wait(
            (chat_task, next_event_task),
            timeout=15,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if next_event_task in completed:
            return next_event_task.result()
        return None
    finally:
        # 超时、聊天完成或连接取消后，不留下仍在等待队列的任务。
        if not next_event_task.done():
            next_event_task.cancel()
        await asyncio.gather(next_event_task, return_exceptions=True)


def _encode_sse(event: str, data: dict) -> str:
    """把事件编码为前端约定的 SSE 文本；只拼字符串，不需要协程。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _process_chat(request: ChatRequest, current_user: dict, on_progress=None, on_delta=None, on_event=None) -> ChatResponse:
    """聊天主流程：读会话、准备技能和素材、执行业务分支、保存结果。"""
    request_id = str(uuid.uuid4())[:8]
    user_id = current_user["id"]
    session_id = request.session_id or None
    if request.prompt_optimization and not (request.skill_id or '').strip():
        raise HTTPException(status_code=400, detail='请先选择技能，再优化提示词')
    canvas = _require_canvas(request.canvas_id, user_id)
    started_at = time.perf_counter()
    logger.info(
        "工作流对话开始 request_id=%s user_id=%s session_id=%s message_length=%d",
        request_id, user_id, session_id or "new", len(request.message),
    )

    # 1. 读取历史，并确认会话属于当前用户。新会话返回 None。
    # existing_state 是模型看到的历史，不等于数据库里的生成任务列表。
    existing_state = await asyncio.to_thread(_load_chat_state, session_id, user_id, request.canvas_id)
    # 两个字段代表互斥阶段：提示词优化阶段不能夹带已确认的生成参数。
    if request.prompt_optimization and request.generation_options:
        raise HTTPException(status_code=400, detail='提示词优化不能同时提交生成任务')
    if request.prompt_optimization and request.skill_id == 'image-prompt-reverse' and not request.optimization_node_id:
        raise HTTPException(status_code=400, detail='反推提示词缺少目标节点编号')
    if request.prompt_optimization and request.optimization_node_id:
        document = json.loads(canvas['document']) if isinstance(canvas['document'], str) else canvas['document']
        tasks = await asyncio.to_thread(lambda: refresh_tasks(
            WorkflowRepository.get_canvas_executions(request.canvas_id, user_id), user_id))
        document = apply_tasks(document, tasks)
        reverse = request.skill_id == 'image-prompt-reverse'
        node_assets, node_mentions = node_reference_images(document, request.optimization_node_id, required=False)
        if reverse:
            request.asset_ids = list(dict.fromkeys([*request.asset_ids, *node_assets]))
            assets = await asyncio.to_thread(load_chat_assets, request.asset_ids, user_id) if request.asset_ids else []
            image_ids = [asset['id'] for asset in assets if asset['asset_type'] == 'picture']
            if not image_ids:
                raise HTTPException(status_code=400, detail='请先在助手中选择或上传图片，或连接上游图片节点，再反推提示词')
            if len(image_ids) > 10:
                raise HTTPException(status_code=400, detail='反推提示词最多支持 10 张图片')
            request.asset_ids = image_ids
            request.asset_mentions = {asset_id: f'@图片{index}' for index, asset_id in enumerate(image_ids, 1)}
        else:
            request.asset_ids = list(dict.fromkeys([*node_assets, *request.asset_ids]))
            request.asset_mentions = {**request.asset_mentions, **node_mentions}
            if len(request.asset_ids) > 10:
                raise HTTPException(status_code=400, detail='每条消息最多引用 10 个素材')
    # 资产先从数据库加载，再转换成模型可读的文本/图片内容。
    assets = await asyncio.to_thread(load_chat_assets, request.asset_ids, user_id) if request.asset_ids else []
    user_content = await asyncio.to_thread(build_asset_content, request.message, assets, request.asset_mentions)
    skill_instruction = ''
    skill_trace = None
    # 普通生成的暂停草稿保留原技能；节点优化每轮必须显式选择技能。
    saved_skill = (((existing_state or {}).get('generation_draft') or {}).get('skill_id')
                   if not request.prompt_optimization else None)
    skill_id = request.skill_id or saved_skill
    if skill_id and not request.generation_options:
        # SkillManager 只负责读取技能文件；技能文本随后作为 system 规则交给对话模型。
        try:
            skill_instruction = await asyncio.to_thread(lambda: SkillManager().get_instruction(skill_id))
        except ValueError as error:
            logger.warning(
                "Skill调用失败 request_id=%s skill_id=%s error=%s",
                request_id, skill_id, error,
            )
            raise HTTPException(status_code=400, detail=str(error)) from error
        skill_trace = {
            "type": "skill_call",
            "skill_id": skill_id,
            "status": "loaded",
            "instruction_chars": len(skill_instruction),
            "message": "已加载技能规则，将用于本轮模型请求",
        }
        logger.info(
            "Skill规则已加载 request_id=%s skill_id=%s status=loaded instruction_chars=%d prompt_optimization=%s",
            request_id, skill_id, len(skill_instruction), request.prompt_optimization,
        )

    # 2. 新会话延迟到工具真正提交任务，或聊天成功后再创建。
    # 这样“只追问/只优化但失败”的请求不会产生空的工作流会话。
    def ensure_session():
        nonlocal session_id
        if session_id is None:
            session_id = WorkflowRepository.create_session(user_id, request.canvas_id)
        return session_id

    user_conversation_id = None

    def ensure_conversation():
        nonlocal user_conversation_id
        if user_conversation_id is None:
            user_conversation_id = WorkflowRepository.add_conversation(
                ensure_session(), "user", request.message, asset_ids=request.asset_ids,
                metadata={"asset_mentions": request.asset_mentions, **({'skill_id': request.skill_id} if request.skill_id else {}),
                          **({'prompt_optimization': True} if request.prompt_optimization else {})},
            )
        return user_conversation_id

    # generation_options 为空时用于普通图执行；非空时用于确认阶段校验。
    generation_options = request.generation_options or {}
    workflow_tools = WorkflowTools(current_user, ensure_session, generation_options, ensure_conversation, canvas_id=request.canvas_id)
    workflow_tools.asset_ids = [asset["id"] for asset in assets]
    workflow_tools.asset_mentions = request.asset_mentions
    for previous_message in (existing_state or {}).get("messages", []):
        workflow_tools.allowed_asset_ids.update(previous_message.get("asset_ids", []))
    workflow_tools.allowed_asset_ids.update(workflow_tools.asset_ids)
    # 读取旧任务只用于本轮响应和历史展示，不会重新提交这些任务。
    previous_tasks = session_tasks(session_id, user_id) if session_id else []
    events = []

    async def record_event(event: str, data: dict):
        # 同一份事件写入数据库 metadata，并通过 SSE 推送给前端执行轨迹。
        if event == "trace":
            events.append(data)
            if data.get("type") == "model_request" and skill_instruction:
                logger.info(
                    "Skill随模型请求发送 request_id=%s skill_id=%s model=%s round=%s instruction_chars=%d",
                    request_id, skill_id, data.get("model"), data.get("round"), len(skill_instruction),
                )
        if on_event:
            await on_event(event, data)

    if skill_trace:
        await record_event("trace", skill_trace)

    async def canvas_changed():
        await record_event('canvas_changed', {'canvas_id': request.canvas_id})

    workflow_tools.on_canvas_change = canvas_changed

    # 3. 三类请求走不同分支：节点提示词优化、确认面板提交、普通对话图执行。
    #    普通生成计划要先优化步骤提示词，再由工具返回 selection_required 打开参数面板。
    if request.prompt_optimization:
        # 节点提示词优化：只调用文字模型，返回 optimized_prompt，不触发生成工具。
        result = await _run_prompt_optimization(request, existing_state, user_content, skill_instruction, on_progress, on_delta, record_event)
    elif generation_options:
        # 参数确认阶段：只接受上一次服务端保存的 pending generation，防止客户端篡改依赖。
        pending = (existing_state or {}).get("generation_request")
        if not pending or pending["media_type"] != generation_options.get("media_type"):
            raise HTTPException(status_code=400, detail="生成请求已变化，请重新发起生成并确认参数")
        pending = _apply_generation_edits(pending, generation_options)
        input_asset_ids = pending.get("input_asset_ids", [])
        workflow_tools.allowed_asset_ids.update(input_asset_ids)
        tool_name = 'generation_plan' if pending['media_type'] == 'plan' else (pending.get("tool_name") or ("txt2img" if pending["media_type"] == "image" else "txt2video"))
        tool_input = {'steps': pending['steps']} if pending['media_type'] == 'plan' else {"prompt": pending["prompt"], "input_asset_ids": input_asset_ids}
        await record_event("trace", {"type": "tool_call", "round": 1,
            "call_id": "confirmed-generation", "name": tool_name, "input": tool_input})
        task = await workflow_tools.confirm_plan(pending) if tool_name == 'generation_plan' else await workflow_tools.discover_and_execute(tool_name, tool_input)
        await record_event("trace", {"type": "tool_result", "round": 1,
            "call_id": "confirmed-generation", "name": tool_name, "output": task})
        if task.get("error"):
            raise HTTPException(status_code=502, detail=str(task["error"]))
        if task.get('plan_id'):
            result = {'reply': '任务计划已提交，节点和连线已创建，关闭页面后后台仍会继续执行。',
                      'state': {'intent': 'generation_plan'}, 'tasks': task['tasks'], 'workflow_ready': True}
        elif task.get("task_id"):
            reply = "生成任务已提交，请查看下方进度。"
            result = {"reply": reply, "state": {"intent": "batch_image" if tool_name in ("txt2img", "img2img") else "text_to_video"}, "tasks": [task], "workflow_ready": True}
        elif task.get("selection_required"):
            workflow_tools.pending_generation = task["selection_required"]
            result = {"reply": "请在弹出的选择框中补全生成参数。", "state": existing_state, "tasks": [], "workflow_ready": False}
        else:
            raise HTTPException(status_code=502, detail="生成任务未提交，请重试")
        if on_delta:
            await on_delta(result["reply"])
    else:
        # 首次生成请求：LangGraph 负责意图识别、提示词优化和工具调用。
        result = await _run_conversation_graph(
            request=request,
            workflow_tools=workflow_tools,
            existing_state=existing_state,
            user_content=user_content,
            request_id=request_id,
            on_progress=on_progress,
            on_delta=on_delta,
            on_event=record_event,
            skill_instruction=skill_instruction,
        )

    # 4. 保存本轮对话和会话状态。会话 parameters 只保存待确认请求；
    #    已提交任务的状态和参数以 workflow_executions 为准。
    # 5. 统一落库并返回；无论走哪个分支，都在这里生成会话和对话记录。
    session_id = ensure_session()
    pending_generation = workflow_tools.pending_generation if isinstance(workflow_tools.pending_generation, dict) else None
    generation_draft = result.get('generation_draft')
    if generation_draft:
        generation_draft['skill_id'] = skill_id
    if pending_generation:
        result["state"]["intent"] = {'image': 'batch_image', 'video': 'text_to_video', 'plan': 'generation_plan'}[pending_generation['media_type']]
    result["metadata"] = {"events": events, "context_usage": result.get("context_usage")}
    if result.get('optimized_prompt'):
        result['metadata']['optimized_prompt'] = result['optimized_prompt']
    if request.asset_ids or request.skill_id or request.prompt_optimization:
        ensure_conversation()
    user_conversation_id, agent_conversation_id = _save_chat_result(
        session_id, request.message, result, previous_tasks, user_conversation_id
    )
    # 两种等待状态分开存：generation_draft 等待补充/重试，generation_request 等待参数确认。
    # 草稿不会发给前端参数弹窗，也不会创建执行记录；无需新增数据库字段。
    if pending_generation:
        WorkflowRepository.update_session(session_id, parameters={"generation_request": pending_generation})
    elif generation_draft:
        WorkflowRepository.update_session(session_id, parameters={"generation_draft": generation_draft})
    elif not request.prompt_optimization:
        # 正常生成已就绪、已提交，或用户已取消/换任务时，清掉旧草稿和旧参数请求。
        WorkflowRepository.update_session(session_id, parameters={})
    logger.info(
        "工作流对话完成 request_id=%s session_id=%s intent=%s workflow_ready=%s elapsed_ms=%d",
        request_id, session_id, result["state"].get("intent"),
        result.get("workflow_ready", False), round((time.perf_counter() - started_at) * 1000),
    )
    return ChatResponse(
        reply=result["reply"],
        optimized_prompt=result.get('optimized_prompt'),
        session_id=session_id,
        user_conversation_id=user_conversation_id,
        agent_conversation_id=agent_conversation_id,
        intent=result["state"].get("intent"),
        workflow_ready=result.get("workflow_ready", False),
        tasks=session_tasks(session_id, user_id),
        generation_request=pending_generation,
        context_usage=result.get("context_usage"),
    )


async def _run_prompt_optimization(request, existing_state, user_content, skill_instruction, on_progress, on_delta, on_event):
    """画布节点提示词优化分支。

    它和普通生成图完全独立：模型返回 question 时继续对话，返回 ready 时回传
    optimized_prompt；两种情况都不会调用图片/视频生成接口。
    """
    client, model_name, context_window = _get_llm_client(request.model_id)
    messages = [{'role': 'system', 'content': (
        '你正在帮助用户优化画布节点的图片或视频提示词。只编写提示词，不执行生成任务。'
        '按用户所选技能要求进行多轮沟通，缺少比例、时长等关键信息时先追问，不得擅自猜测。'
        '已有节点参数视为用户当前选择，不重复询问；保留引用素材的 @图片、@视频 编号。\n\n' + skill_instruction
    )}]
    messages.extend({key: message[key] for key in ('role', 'content')} for message in (existing_state or {}).get('messages', []))
    messages.append({'role': 'user', 'content': user_content})
    messages.append({'role': 'system', 'content': (
        '只返回 JSON 对象。需要追问时返回 {"status":"question","reply":"问题"}。'
        '完成时返回 {"status":"ready","reply":"完整的优化结果","prompt":"最终提示词"}。'
        'prompt 必须是可直接回填的单一完整提示词，不含说明、追问、代码块围栏或多个备选方案。'
        '技能规则适用于字段内的内容，不得覆盖此返回格式。'
    )})
    if on_progress:
        await on_progress('正在优化提示词…')
    # 纯优化分支允许按技能追问，但 ready 中的 prompt 同样不能是问题句，
    # 否则前端“应用提示词”会把反问填回画布。纠正次数与实际生成链路一致。
    for attempt in range(2):
        await on_event('trace', {'type': 'model_request', 'round': attempt + 1, 'model': model_name, 'message_count': len(messages), 'tools': []})
        response = await client.chat.completions.create(model=model_name, messages=messages, response_format={'type': 'json_object'})
        usage = read_model_usage(response, model_name)
        if usage:
            usage['max_tokens'] = context_window
            await on_event('usage', usage)
        raw_content = None
        try:
            raw_content = response.choices[0].message.content
            content = json.loads(raw_content)
            if not isinstance(content, dict) or content.get('status') not in ('question', 'ready'):
                raise ValueError('无效状态')
            reply = content.get('reply')
            if content['status'] == 'question':
                if not isinstance(reply, str) or not reply.strip() or content.get('prompt') is not None:
                    raise ValueError('追问必须只有非空 reply')
                prompt = None
            else:
                # ready 只要求 prompt；reply 是兼容旧模型的可选说明，但不会回填画布。
                prompt = validate_final_prompt(content.get('prompt'))
                reply = reply.strip() if isinstance(reply, str) and reply.strip() else prompt
        except (ValueError, TypeError, AttributeError, IndexError) as error:
            if attempt:
                raise HTTPException(status_code=502, detail='提示词优化未返回有效结果，请重试') from error
            messages.extend([
                {'role': 'assistant', 'content': raw_content if isinstance(raw_content, str) else ''},
                {'role': 'system', 'content': f'上一结果校验失败：{error}。请重新按协议返回；需要询问用户时用 question，最终提示词中不得含对用户的追问。'},
            ])
            continue
        break
    if on_delta:
        await on_delta(reply)
    return {'reply': reply, 'optimized_prompt': prompt.strip() if prompt else None,
            'state': {'intent': 'chat'}, 'tasks': [], 'workflow_ready': False, 'context_usage': usage}


def _require_canvas(canvas_id: int, user_id: int):
    canvas = canvas_repo.get_canvas(canvas_id, user_id)
    if not canvas:
        raise HTTPException(status_code=404, detail="画布不存在")
    return canvas


def _require_session(session_id: int, user_id: int, canvas_id: int):
    _require_canvas(canvas_id, user_id)
    session = WorkflowRepository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session["user_id"] != user_id or session.get('canvas_id') != canvas_id:
        raise HTTPException(status_code=403, detail="会话不属于当前画布")
    return session


def _load_chat_state(session_id: Optional[int], user_id: int, canvas_id: int) -> Optional[ConversationState]:
    """恢复已有会话的权限、历史消息和参数；新会话暂不写数据库。"""
    if not session_id:
        return None

    session = _require_session(session_id, user_id, canvas_id)

    conversations = WorkflowRepository.get_conversations(session_id)

    def _normalize_role(role: str) -> str:
        """将数据库角色映射到 LangChain 支持的消息类型"""
        role_map = {"agent": "assistant", "user": "user", "human": "user"}
        return role_map.get(role, "user")

    return {
        "session_id": session_id,
        "user_id": user_id,
        "messages": [
            {"role": _normalize_role(item["role"]), "content": build_asset_content(item["message"], load_chat_assets(item["asset_ids"], user_id), item.get("metadata", {}).get("asset_mentions"))
             if item.get("asset_ids") else item["message"], "asset_ids": item.get("asset_ids", [])}
            for item in conversations
        ],
        "intent": session.get("intent"),
        "generation_request": session.get("parameters", {}).get("generation_request"),
        "generation_draft": session.get("parameters", {}).get("generation_draft"),
        "missing_params": [],
        "workflow_ready": session["status"] == "ready",
        "current_step": "parameter_extraction" if session.get("intent") else "intent_recognition",
    }


def _save_chat_result(
    session_id: int, message: str, result: dict, previous_tasks: list,
    user_conversation_id: Optional[int] = None,
):
    """保存用户和助手消息；根据本轮提交情况更新会话状态。"""
    if user_conversation_id is None:
        user_conversation_id = WorkflowRepository.add_conversation(session_id, "user", message)
    agent_conversation_id = WorkflowRepository.add_conversation(
        session_id, "agent", result["reply"], metadata=result.get("metadata")
    )

    state = result["state"]
    if result.get("tasks"):
        WorkflowRepository.update_session(
            session_id,
            intent=state.get("intent"),
            status="executing",
        )
    elif state.get("intent") and not previous_tasks:
        WorkflowRepository.update_session(
            session_id,
            intent=state["intent"],
            status="collecting",
        )

    return user_conversation_id, agent_conversation_id


class SessionResponse(BaseModel):
    id: int
    canvas_id: int
    title: Optional[str] = None
    intent: Optional[str]
    status: str
    created_at: str
    updated_at: str


@router.get("/sessions", response_model=List[SessionResponse])
async def get_sessions(canvas_id: int, current_user: dict = Depends(get_current_user)):
    """获取用户的会话列表"""
    user_id = current_user["id"]
    _require_canvas(canvas_id, user_id)
    sessions = WorkflowRepository.get_user_sessions(user_id, canvas_id)

    return [
        SessionResponse(
            id=s["id"],
            canvas_id=s['canvas_id'],
            title=s.get('title'),
            intent=s["intent"],
            status=s["status"],
            created_at=s["created_at"].isoformat(),
            updated_at=s["updated_at"].isoformat()
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: int, canvas_id: int, current_user: dict = Depends(get_current_user)):
    """软删除当前用户的会话。"""
    user_id = current_user["id"]
    _require_session(session_id, user_id, canvas_id)
    WorkflowRepository.soft_delete_session(session_id, user_id)


@router.post('/plans/{plan_id}/retry')
async def retry_generation_plan(plan_id: str, canvas_id: int, current_user: dict = Depends(get_current_user)):
    from agents.services.plan_scheduler import retry_plan
    _require_canvas(canvas_id, current_user['id'])
    await asyncio.to_thread(retry_plan, plan_id, current_user['id'], canvas_id)
    return {'status': 'running'}


class SessionDetailResponse(BaseModel):
    id: int
    canvas_id: int
    intent: Optional[str]
    generation_request: Optional[Dict[str, Any]] = None
    status: str
    conversations: List[Dict[str, Any]]
    tasks: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(session_id: int, canvas_id: int, current_user: dict = Depends(get_current_user)):
    """获取会话详情"""
    user_id = current_user["id"]

    session = _require_session(session_id, user_id, canvas_id)

    conversations = WorkflowRepository.get_conversations(session_id)

    return SessionDetailResponse(
        id=session["id"],
        canvas_id=canvas_id,
        intent=session.get("intent"),
        generation_request=session.get("parameters", {}).get("generation_request"),
        status=session["status"],
        tasks=session_tasks(session_id, user_id),
        conversations=[
            {
                "id": conv["id"],
                "role": conv["role"],
                "message": conv["message"],
                "created_at": conv["created_at"].isoformat(),
                "assets": asset_previews(load_chat_assets(conv["asset_ids"], user_id)) if conv.get("asset_ids") else [],
                "events": conv.get("metadata", {}).get("events", []),
                "context_usage": conv.get("metadata", {}).get("context_usage"),
            }
            for conv in conversations
        ]
    )
