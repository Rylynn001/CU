"""累计图内调用次数，结束条件统一由 should_continue 判断。"""


def check_done_node(state):
    return {'loop_count': state.get('loop_count', 0) + 1}
