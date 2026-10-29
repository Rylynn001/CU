"""
完整的 Seedance 工具集成测试
模拟真实的对话流程
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.workflow_tools import WorkflowTools


class MockUser:
    """模拟用户对象"""
    def __init__(self):
        self.data = {
            "id": 1,
            "user_id": 1,
            "username": "test_user"
        }

    def __getitem__(self, key):
        return self.data[key]


class MockSession:
    """模拟 session 管理"""
    def __init__(self):
        self.session_id = "test_session_001"

    def __call__(self):
        return self.session_id


async def test_tool_discovery():
    """测试工具发现机制"""
    print("=== 测试 1: 工具发现 ===\n")

    user = MockUser()
    session = MockSession()
    tools = WorkflowTools(user, session)

    test_queries = [
        "我想生成一个视频的提示词",
        "帮我写个 seedance 提示词",
        "做一个 30 秒的短剧",
        "图生视频怎么写提示词",
    ]

    for query in test_queries:
        discovered = tools.discover(query)
        print(f"查询: '{query}'")
        print(f"发现工具: {[t['function']['name'] for t in discovered]}")
        if discovered and discovered[0]['function']['name'] == 'generate_seedance_prompt':
            print("  [OK] 成功发现 Seedance 工具")
        print()


async def test_tool_execution():
    """测试工具执行"""
    print("\n=== 测试 2: 工具执行 ===\n")

    user = MockUser()
    session = MockSession()
    tools = WorkflowTools(user, session)

    # 模拟 LLM 调用工具
    arguments = {
        "request": "帮我生成一个 30 秒的赛博朋克城市夜景视频，主角是穿着发光外套的女黑客",
        "version": "2.5",
        "duration": 30,
        "aspect_ratio": "16:9"
    }

    print("调用参数:")
    print(json.dumps(arguments, ensure_ascii=False, indent=2))
    print()

    try:
        result = await tools._generate_seedance_prompt(arguments)
        print("返回结果:")
        print(f"  路径: {result.get('path')}")
        print(f"  版本: {result.get('version')}")
        print(f"  消息: {result.get('message')}")
        print()
        print("生成的指令(前 800 字符):")
        instruction = result.get('instruction', '')
        print(instruction[:800])
        if len(instruction) > 800:
            print("...")
        print()
        print("  [OK] 工具执行成功")
    except Exception as e:
        print(f"  [X] 执行失败: {e}")
        import traceback
        traceback.print_exc()


async def test_workflow_integration():
    """测试完整工作流集成"""
    print("\n=== 测试 3: 工作流集成 ===\n")

    user = MockUser()
    session = MockSession()
    tools = WorkflowTools(user, session)

    # 场景 1: 图生视频
    print("场景 1: 图生视频")
    args1 = {
        "request": "我有一张产品图，想做成旋转展示的广告视频，9:16 竖屏",
        "aspect_ratio": "9:16"
    }
    result1 = await tools._generate_seedance_prompt(args1)
    print(f"  路径: {result1['path']} (期望: C - 图生视频)")
    print(f"  版本: {result1['version']}")
    print()

    # 场景 2: 长视频
    print("场景 2: 长视频制作")
    args2 = {
        "request": "制作一个 60 秒的完整短剧，有起承转合",
        "duration": 60
    }
    result2 = await tools._generate_seedance_prompt(args2)
    print(f"  路径: {result2['path']} (期望: B - 长视频流水线)")
    print(f"  版本: {result2['version']}")
    print()

    # 场景 3: 概念视频
    print("场景 3: 概念短视频")
    args3 = {
        "request": "一个炫酷的产品开箱视频，15 秒",
        "duration": 15,
        "version": "2.0"
    }
    result3 = await tools._generate_seedance_prompt(args3)
    print(f"  路径: {result3['path']} (期望: A - 概念驱动)")
    print(f"  版本: {result3['version']} (期望: 2.0)")
    print()

    print("  [OK] 工作流集成测试完成")


async def test_all_tools():
    """测试所有注册的工具"""
    print("\n=== 测试 4: 所有工具列表 ===\n")

    user = MockUser()
    session = MockSession()
    tools = WorkflowTools(user, session)

    print("已注册的工具:")
    for name, tool_def in tools.tools.items():
        func = tool_def['function']
        print(f"  - {func['name']}: {func['description'][:60]}...")

    print()
    has_seedance = 'generate_seedance_prompt' in tools.tools
    print(f"  [OK] Seedance 工具已注册" if has_seedance else "  [X] Seedance 工具未注册")


async def main():
    """运行所有测试"""
    print("╔═══════════════════════════════════════════════╗")
    print("║   Seedance 工具集成完整测试                  ║")
    print("╚═══════════════════════════════════════════════╝")
    print()

    await test_all_tools()
    await test_tool_discovery()
    await test_tool_execution()
    await test_workflow_integration()

    print()
    print("╔═══════════════════════════════════════════════╗")
    print("║   所有测试完成                                ║")
    print("╚═══════════════════════════════════════════════╝")


if __name__ == "__main__":
    asyncio.run(main())
