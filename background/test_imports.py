"""
测试所有关键模块的导入
"""
import sys

def test_imports():
    """测试所有关键导入"""
    errors = []

    # 测试列表
    tests = [
        ("main", "from main import app"),
        ("workflow API", "from api.workflow import router"),
        ("auth", "from api.auth import get_current_user"),
        ("conversation agent", "from agents.conversation_agent import ConversationAgent"),
        ("workflow repo", "from repositories.workflow_repo import WorkflowRepository"),
        ("graph states", "from graph.states import ConversationState"),
    ]

    for name, import_stmt in tests:
        try:
            exec(import_stmt)
            print(f"[OK] {name}")
        except Exception as e:
            error_msg = f"[FAIL] {name}: {str(e)}"
            print(error_msg)
            errors.append(error_msg)

    if errors:
        print(f"\nFound {len(errors)} import errors")
        return 1
    else:
        print("\nAll imports passed!")
        return 0

if __name__ == "__main__":
    sys.exit(test_imports())
