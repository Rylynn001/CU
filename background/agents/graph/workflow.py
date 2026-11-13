"""
LangGraph 对话工作流主图编排

架构:
    START → intent → [prompt_enhance | direct_execute] → execute_tool → check_done → [END | intent]

    prompt_enhance 是子图: analyze → generate_ins → enhance
"""
import logging
from typing import Optional, Callable, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .states import ConversationState
from .nodes.intent_node import intent_recognition_node
from .nodes.tool_node import direct_execute_node, execute_tool_node
from .nodes.check_node import check_done_node
from .subgraphs.prompt_enhance import create_prompt_enhance_subgraph
from .utils.routing import should_optimize_prompt, should_continue

logger = logging.getLogger(__name__)

MAX_LOOP = 8  # 最大循环次数


def create_conversation_workflow(
    workflow_tools=None,
    llm_client=None,
    checkpointer=None
):
    """
    创建对话工作流主图

    Args:
        workflow_tools: WorkflowTools 实例(工具执行器)
        llm_client: AsyncOpenAI 实例(LLM 客户端，用于子图优化)
        checkpointer: LangGraph checkpointer，默认 MemorySaver

    Returns:
        编译好的 LangGraph 工作流
    """
    # 1. 创建主图
    workflow = StateGraph(ConversationState)

    # 2. 准备节点闭包(注入依赖)
    async def _execute_tool(state):
        return await execute_tool_node(state, workflow_tools=workflow_tools)

    # 3. 添加普通节点
    workflow.add_node("intent", intent_recognition_node)
    workflow.add_node("direct_execute", direct_execute_node)
    workflow.add_node("execute_tool", _execute_tool)
    workflow.add_node("check_done", check_done_node)

    # 4. 添加子图节点，并包一层 state 转换（主图 state → 子图 state）
    prompt_subgraph = create_prompt_enhance_subgraph(llm_client=llm_client)

    async def _prompt_enhance_wrapper(state):
        """将主图 state 转为子图 state 并执行子图，结果合并回主图"""
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else None
        if last_msg is None:
            return {}
        user_prompt = last_msg.content if hasattr(last_msg, "content") else last_msg.get("content", "")

        sub_input = {
            "user_prompt": user_prompt,
            "intent": state.get("intent", "txt2video"),
            "enhanced_prompt": None,
            "seedance_version": None,
            "seedance_path": None,
            "instruction": None,
        }
        sub_result = await prompt_subgraph.ainvoke(sub_input)

        # 把优化后的提示词写到 generation_request
        enhanced = sub_result.get("enhanced_prompt", user_prompt)
        return {
            "current_tool": "txt2video" if state.get("intent") == "txt2video" else "txt2img",
            "generation_request": {"prompt": enhanced}
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

    # 7. 子图出口 + 直接执行 → 工具执行
    workflow.add_edge("prompt_enhance", "execute_tool")
    workflow.add_edge("direct_execute", "execute_tool")

    # 8. 工具执行 → 完成检查
    workflow.add_edge("execute_tool", "check_done")

    # 9. 完成检查 → END 或循环回 intent
    workflow.add_conditional_edges(
        "check_done",
        should_continue,
        {END: END, "intent": "intent"}
    )

    # 10. 配置检查点
    if checkpointer is None:
        checkpointer = MemorySaver()

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
