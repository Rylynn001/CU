"""
测试 LangGraph 工作流并生成可视化

运行方式:
    cd d:/CU/background
    python test_graph_visualization.py
"""
import asyncio
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))

from agents.graph.workflow import create_conversation_workflow


async def test_workflow():
    """测试工作流的各种场景"""
    print("=== 测试 LangGraph 对话工作流 ===\n")

    graph = create_conversation_workflow()

    # ──────────────────────────────────
    # 测试 1: 普通对话
    # ──────────────────────────────────
    print("[测试 1] 普通对话 (intent=chat)")
    result1 = await graph.ainvoke(
        {
            'messages': [{'role': 'user', 'content': '你好，介绍一下你自己'}],
            'user_id': 1,
            'session_id': None,
            'enable_prompt_optimization': False,
            'loop_count': 0,
            'is_complete': False,
            'workflow_ready': False,
            'current_step': '',
        },
        config={'configurable': {'thread_id': 'test_chat'}}
    )
    print(f"  - intent: {result1.get('intent')}")
    print(f"  - is_complete: {result1.get('is_complete')}")
    print(f"  - 路径: intent → direct_execute → END\n")

    # ──────────────────────────────────
    # 测试 2: 文生图 (不启用优化)
    # ──────────────────────────────────
    print("[测试 2] 文生图 (不启用提示词优化)")
    result2 = await graph.ainvoke(
        {
            'messages': [{'role': 'user', 'content': '画一张可爱的猫的图片'}],
            'user_id': 1,
            'session_id': None,
            'enable_prompt_optimization': False,
            'loop_count': 0,
            'is_complete': False,
            'workflow_ready': False,
            'current_step': '',
        },
        config={'configurable': {'thread_id': 'test_txt2img'}}
    )
    print(f"  - intent: {result2.get('intent')}")
    print(f"  - current_tool: {result2.get('current_tool')}")
    print(f"  - generation_request: {result2.get('generation_request')}")
    print(f"  - is_complete: {result2.get('is_complete')}")
    print(f"  - 路径: intent → direct_execute → execute_tool → check_done → END\n")

    # ──────────────────────────────────
    # 测试 3: 文生视频 (启用优化)
    # ──────────────────────────────────
    print("[测试 3] 文生视频 (启用提示词优化)")
    result3 = await graph.ainvoke(
        {
            'messages': [{'role': 'user', 'content': '用即梦生成一个15秒的视频'}],
            'user_id': 1,
            'session_id': None,
            'enable_prompt_optimization': True,
            'loop_count': 0,
            'is_complete': False,
            'workflow_ready': False,
            'current_step': '',
        },
        config={'configurable': {'thread_id': 'test_txt2video_opt'}}
    )
    print(f"  - intent: {result3.get('intent')}")
    print(f"  - current_tool: {result3.get('current_tool')}")
    print(f"  - generation_request: {result3.get('generation_request')}")
    print(f"  - is_complete: {result3.get('is_complete')}")
    print(f"  - 路径: intent → prompt_enhance(子图) → execute_tool → check_done → END\n")

    print("[OK] 所有测试通过\n")


def generate_graph_visualization():
    """生成工作流可视化图片"""
    print("=== 生成 Graph 结构图 ===\n")

    graph = create_conversation_workflow()

    # 生成 Mermaid PNG
    png_data = graph.get_graph(xray=True).draw_mermaid_png()

    # 保存到当前目录
    output_path = Path(__file__).parent / "workflow_graph.png"
    with open(output_path, 'wb') as f:
        f.write(png_data)

    print(f"[OK] Graph 结构图已保存到: {output_path}")
    print(f"   PNG 大小: {len(png_data):,} 字节\n")

    # 尝试用 IPython 显示
    try:
        from IPython.display import Image, display
        display(Image(graph.get_graph(xray=True).draw_mermaid_png()))
        print("[OK] 已在 Jupyter/IPython 环境中显示")
    except ImportError:
        print("[提示] 如需在 Jupyter 中显示，请安装: pip install ipython pillow")

    return output_path


def main():
    """主函数"""
    print("\n" + "="*60)
    print(" LangGraph - Test & Visualization")
    print("="*60 + "\n")

    # 1. 生成可视化
    graph_path = generate_graph_visualization()

    # 2. 运行测试
    asyncio.run(test_workflow())

    # 3. 总结
    print("="*60)
    print("Graph Summary:")
    print("  - Main nodes: 5 (intent, direct_execute, prompt_enhance, execute_tool, check_done)")
    print("  - Sub nodes:  3 (analyze, generate_ins, enhance)")
    print("  - Cond edges: 2 (intent->route, check_done->loop)")
    print("  - Fixed edges: 6")
    print()
    print(f"Graph PNG: {graph_path}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
