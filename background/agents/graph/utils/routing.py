"""聊天图的条件路由；多步生成交由后台计划调度，不在图内等待。"""
from langgraph.graph import END


def should_optimize_prompt(state):
    return 'prompt_enhance' if state.get('enable_prompt_optimization') and state.get('intent') == 'txt2video' else 'direct_execute'


def should_continue(state):
    waiting = (state.get('tool_result') or {}).get('selection_required')
    return END if state.get('is_complete') or state.get('loop_count', 0) >= 8 or waiting else 'intent'
