"""
LangGraph 对话工作流主图编排

架构:
    START → intent → [prompt_enhance | direct_execute] → execute_tool → check_done → [END | intent]

    prompt_enhance 是子图: analyze → generate_ins → enhance
"""
from typing import Optional
from langgraph.graph import StateGraph, END

from .states import ConversationState
from .nodes.intent_node import intent_recognition_node
from .nodes.tool_node import direct_execute_node, execute_tool_node
from .nodes.check_node import check_done_node
from .subgraphs.prompt_enhance import create_prompt_enhance_subgraph, llm_enhance_node
from .utils.routing import should_optimize_prompt, should_continue
from .utils.usage import read_model_usage
from agents.skill_agent import SkillManager

def create_conversation_workflow(
    workflow_tools=None,
    llm_client=None,
    model_name: Optional[str] = None,
    checkpointer=None,
    on_event=None,
    skill_instruction: str = '',
):
    """
    创建对话工作流主图

    Args:
        workflow_tools: WorkflowTools 实例(工具执行器)
        llm_client: AsyncOpenAI 实例(LLM 客户端，用于对话和提示词优化)
        model_name: 语言模型名称
        checkpointer: 可选的 LangGraph 检查点；会话历史与长任务从数据库恢复

    Returns:
        编译好的 LangGraph 工作流
    """
    # 1. 创建主图
    workflow = StateGraph(ConversationState)

    # 2. 准备节点闭包(注入依赖)
    model_round = 0
    default_skill_instructions = {}

    def instruction_for(media_type):
        if skill_instruction:
            return skill_instruction
        if media_type not in default_skill_instructions:
            skill_id = 'gpt-image-2-style-library' if media_type == 'image' else 'seedance-prompt'
            try:
                default_skill_instructions[media_type] = SkillManager().get_instruction(skill_id)
            except ValueError:
                default_skill_instructions[media_type] = ''
        return default_skill_instructions[media_type]

    async def report_model_usage(response):
        usage = read_model_usage(response, model_name or 'gpt-4o-mini')
        if on_event:
            await on_event('usage', usage or {
                'model': model_name or 'gpt-4o-mini', 'max_tokens': None,
                'used_tokens': None, 'input_tokens': None, 'output_tokens': None,
            })

    async def report_model_request(state):
        nonlocal model_round
        model_round += 1
        if on_event:
            await on_event("trace", {
                "type": "model_request", "round": model_round,
                "model": model_name or "gpt-4o-mini",
                "message_count": len(state.get("messages", [])), "tools": [],
            })

    async def _direct_execute(state):
        if state.get("intent") == "chat":
            await report_model_request(state)
        return await direct_execute_node(state, llm_client=llm_client, model_name=model_name, on_usage=report_model_usage)

    async def _execute_tool(state):
        tool_name = state.get("current_tool")
        parameters = state.get("generation_request")
        report_tool = on_event and tool_name and parameters and not (state.get("tool_result") or {}).get("reply")
        call_id = f"graph-tool-{model_round}"
        if report_tool:
            await on_event("trace", {"type": "tool_call", "round": model_round,
                "call_id": call_id, "name": tool_name, "input": parameters})
        result = await execute_tool_node(state, workflow_tools=workflow_tools)
        if report_tool:
            await on_event("trace", {"type": "tool_result", "round": model_round,
                "call_id": call_id, "name": tool_name, "output": result.get("tool_result", {})})
        return result

    async def _intent(state):
        await report_model_request(state)
        return await intent_recognition_node(state, llm_client=llm_client, model_name=model_name, on_usage=report_model_usage)

    # 3. 添加普通节点
    workflow.add_node("intent", _intent)
    workflow.add_node("direct_execute", _direct_execute)
    workflow.add_node("execute_tool", _execute_tool)
    workflow.add_node("check_done", check_done_node)

    # 4. 添加子图节点，并包一层 state 转换（主图 state → 子图 state）
    prompt_subgraph = create_prompt_enhance_subgraph(
        llm_client=llm_client, model_name=model_name, on_usage=report_model_usage,
        on_retry=report_model_request,
    )

    async def _prompt_enhance_wrapper(state):
        """将主图 state 转为子图 state 并执行子图，结果合并回主图"""
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else None
        if last_msg is None:
            return {}

        def pause_generation(result, request, enhanced_steps=None, step=None):
            """暂停本轮对话而非取消任务；草稿只保存状态，不创建节点或扣费任务。"""
            clarification = result.get('clarification')
            question = clarification['reply'] if clarification else result['error'] + '，请回复“重试”继续。'
            label = f'当前步骤：{step["label"]}。' if step else ''
            count = len(request['steps']) if state['intent'] == 'generation_plan' else 1
            return {
                'current_tool': None,
                'generation_request': request,
                'generation_draft': {
                    'intent': state['intent'], 'request': request,
                    'enhanced_steps': enhanced_steps or [],
                    'step_id': step['id'] if step else None,
                    'question': question,
                    'status': 'needs_clarification' if clarification else 'retry',
                },
                'tool_result': {'reply': f'已保留 {count} 步任务。{label}\n\n{question}'},
                'is_complete': True,
            }

        # 多步计划中的每个步骤都必须先经过提示词优化，完成后才能进入
        # 参数选择；否则参数面板会展示意图模型的原始步骤描述。
        if state.get("intent") == "generation_plan":
            request = state.get("generation_request") or {}
            steps = request.get("steps") or []
            # 从服务端草稿恢复已优化部分；用户回答追问时不重写整个计划。
            enhanced_steps = list((state.get('generation_draft') or {}).get('enhanced_steps', []))
            completed_ids = {step['id'] for step in enhanced_steps}
            for step in steps:
                if step['id'] in completed_ids:
                    continue
                step_prompt = step.get("prompt", "")
                step_messages = [*messages, {
                    "role": "system",
                    "content": (
                        f'这是已确认生成计划中的当前步骤：{step}。只改写此步骤的提示词。'
                        '结合用户对上次问题的补充，不重新分类整个任务。'
                        'depends_on 表示未来会自动上传的前置生成结果，不得要求用户提前提供这些图片。'
                        '保留角色身份、参考用途和指定视频时长，不编造资产编号。'
                    ),
                }]
                sub_input = {
                    "user_prompt": step_prompt,
                    "messages": step_messages,
                    "intent": "txt2video" if step.get("media_type") == "video" else "txt2img",
                    "enhanced_prompt": None,
                    "seedance_version": None,
                    "seedance_path": None,
                    "instruction": None,
                }
                if llm_client is not None:
                    await report_model_request(state)
                step_skill_instruction = instruction_for(step.get("media_type", "image"))
                if step_skill_instruction:
                    sub_result = await llm_enhance_node(
                        {**sub_input, 'instruction': step_skill_instruction},
                        llm_client=llm_client, model_name=model_name, on_usage=report_model_usage,
                        on_retry=lambda: report_model_request(state),
                    )
                else:
                    sub_result = await prompt_subgraph.ainvoke(sub_input)
                if sub_result.get("clarification") or sub_result.get("error"):
                    return pause_generation(sub_result, request, enhanced_steps, step)
                enhanced_steps.append({**step, "prompt": sub_result["enhanced_prompt"]})
            return {
                "current_tool": "generation_plan",
                "generation_request": {**request, "steps": enhanced_steps},
                "generation_draft": None,
            }

        user_prompt = (state.get("generation_request") or {}).get("prompt")
        if not user_prompt:
            user_prompt = last_msg.content if hasattr(last_msg, "content") else last_msg.get("content", "")

        sub_input = {
            "user_prompt": user_prompt,
            "messages": messages,
            "intent": state.get("intent", "txt2video"),
            "enhanced_prompt": None,
            "seedance_version": None,
            "seedance_path": None,
            "instruction": None,
        }
        if llm_client is not None:
            await report_model_request(state)
        if instruction_for('video' if state.get('intent') == 'txt2video' else 'image'):
            sub_result = await llm_enhance_node(
                {**sub_input, 'instruction': instruction_for('video' if state.get('intent') == 'txt2video' else 'image')},
                llm_client=llm_client, model_name=model_name, on_usage=report_model_usage,
                on_retry=lambda: report_model_request(state),
            )
        else:
            sub_result = await prompt_subgraph.ainvoke(sub_input)

        if sub_result.get("clarification") or sub_result.get("error"):
            return pause_generation(sub_result, state['generation_request'])

        # 把优化后的提示词写到 generation_request
        enhanced = sub_result["enhanced_prompt"]
        return {
            "current_tool": "txt2video" if state.get("intent") == "txt2video" else "txt2img",
            "generation_request": {**state['generation_request'], "prompt": enhanced},
            "generation_draft": None,
        }

    workflow.add_node("prompt_enhance", _prompt_enhance_wrapper)

    # 5. 设置入口
    workflow.set_entry_point("intent")

    # 6. 添加条件边: intent → direct_execute / prompt_enhance
    workflow.add_conditional_edges(
        "intent",
        should_optimize_prompt,
        {
            "direct_execute": "direct_execute",
            "prompt_enhance": "prompt_enhance"
        }
    )

    # 7. direct_execute 的条件路由：对话完成→check_done，生成→execute_tool
    def route_after_direct_execute(state):
        if state.get("is_complete"):
            return "check_done"
        return "execute_tool"

    workflow.add_conditional_edges(
        "direct_execute",
        route_after_direct_execute,
        {"check_done": "check_done", "execute_tool": "execute_tool"}
    )

    # 8. 追问或优化失败时结束本轮，只有提示词就绪后才执行工具。
    workflow.add_conditional_edges(
        "prompt_enhance",
        route_after_direct_execute,
        {"check_done": "check_done", "execute_tool": "execute_tool"}
    )

    # 9. 工具执行 → 完成检查
    workflow.add_edge("execute_tool", "check_done")

    # 10. 完成检查 → END 或循环回 intent
    workflow.add_conditional_edges(
        "check_done",
        should_continue,
        {END: END, "intent": "intent"}
    )

    return workflow.compile(checkpointer=checkpointer)


# ─────────────────────────────────────────────
# 可视化
# ─────────────────────────────────────────────

def main():
    """
    生成并展示 graph 结构图

    使用方式:
        python -m background.agents.graph.workflow

    依赖:
        pip install ipython pillow
    """
    graph = create_conversation_workflow()

    # 生成 Mermaid PNG 图片
    png_data = graph.get_graph(xray=True).draw_mermaid_png()

    # 保存到文件
    output_path = "workflow_graph.png"
    with open(output_path, "wb") as f:
        f.write(png_data)

    print(f"Graph 结构图已保存到: {output_path}")

    # 尝试用 IPython 显示
    try:
        from IPython.display import Image, display
        display(Image(graph.get_graph(xray=True).draw_mermaid_png()))
        print("已在 Jupyter/IPython 环境中显示 graph 结构图")
    except ImportError:
        print("未安装 IPython，请手动打开 workflow_graph.png 查看")


if __name__ == "__main__":
    main()
