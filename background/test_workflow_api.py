"""
测试工作流 API 客户端
"""
import requests
import json

BASE_URL = "http://localhost:8000/api-proxy/workflow"

# 先登录获取 token（假设已有用户）
def login():
    """登录获取 token"""
    response = requests.post(
        "http://localhost:8000/auth/login",
        json={"username": "admin", "password": "admin123"}  # 需要先创建测试用户
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        print(f"登录失败: {response.text}")
        return None


def chat(token, message, session_id=None):
    """发送对话消息"""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id

    response = requests.post(f"{BASE_URL}/chat", json=payload, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"请求失败: {response.status_code} - {response.text}")
        return None


def test_workflow_chat():
    """测试对话流程"""
    print("=" * 60)
    print("LangGraph 工作流对话测试")
    print("=" * 60)

    # 登录
    print("\n1. 登录...")
    token = login()
    if not token:
        print("无法登录，请先创建测试用户")
        return

    print("登录成功！")

    # 对话流程
    conversations = [
        "我要做一个短剧",
        "我有剧本，内容是关于一个少年的冒险故事",
        "10个分镜",
        "每个5秒",
        "用 ark 模型"
    ]

    session_id = None

    for i, user_message in enumerate(conversations, 1):
        print(f"\n[轮次 {i}]")
        print(f"用户: {user_message}")

        result = chat(token, user_message, session_id)

        if result:
            print(f"Agent: {result['reply']}")
            print(f"工作流就绪: {result['workflow_ready']}")

            session_id = result['session_id']

            if result.get('intent'):
                print(f"意图: {result['intent']}")
            if result.get('parameters'):
                print(f"参数: {json.dumps(result['parameters'], ensure_ascii=False, indent=2)}")

            if result['workflow_ready']:
                print("\n" + "=" * 60)
                print("参数收集完成！")
                print("=" * 60)
                break
        else:
            break

    # 获取会话详情
    if session_id:
        print(f"\n\n2. 获取会话详情...")
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/sessions/{session_id}", headers=headers)
        if response.status_code == 200:
            detail = response.json()
            print(f"\n会话 ID: {detail['id']}")
            print(f"意图: {detail['intent']}")
            print(f"状态: {detail['status']}")
            print(f"参数: {json.dumps(detail['parameters'], ensure_ascii=False, indent=2)}")
            print(f"\n对话记录:")
            for conv in detail['conversations']:
                print(f"  [{conv['role']}] {conv['message']}")


if __name__ == "__main__":
    test_workflow_chat()
