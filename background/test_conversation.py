"""
测试对话 Agent
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.conversation_agent import ConversationAgent
from repositories.generation_repo import get_language_model_info
from config import get_provider_config_by_rfid
from dotenv import load_dotenv

load_dotenv()


async def test_conversation():
    """测试对话流程"""
    # 从数据库获取语言模型配置
    model_info = get_language_model_info('openai')
    if not model_info:
        print("错误：未找到语言模型配置")
        return

    provider_config = get_provider_config_by_rfid(model_info['rfid'])
    if not provider_config:
        print("错误：未找到 provider 配置")
        return

    agent = ConversationAgent(
        api_key=provider_config['api_key'],
        base_url=provider_config['base_url'],
        model=model_info['name']
    )

    session_id = "test-session-001"
    user_id = 1

    print("=" * 60)
    print("LangGraph 对话 Agent 测试")
    print("=" * 60)

    # 模拟对话流程
    conversations = [
        "我要做一个短剧",
        "我有剧本，内容是：...",
        "10个分镜",
        "每个5秒",
        "用 ark 模型"
    ]

    state = None

    for i, user_message in enumerate(conversations, 1):
        print(f"\n[轮次 {i}]")
        print(f"用户: {user_message}")

        result = await agent.process(
            message=user_message,
            session_id=session_id,
            user_id=user_id,
            existing_state=state
        )

        print(f"Agent: {result['reply']}")
        print(f"工作流就绪: {result['workflow_ready']}")

        if result.get("intent"):
            print(f"意图: {result['intent']}")
        if result.get("parameters"):
            print(f"参数: {result['parameters']}")

        state = result["state"]

        if result["workflow_ready"]:
            print("\n" + "=" * 60)
            print("参数收集完成！准备生成工作流...")
            print("=" * 60)
            break


if __name__ == "__main__":
    asyncio.run(test_conversation())
