"""
独立测试脚本 — 无需启动 ComfyUI，直接运行 extractor agent。

用法（在 d:\CU\ 下）：
    python test_agent.py

修改顶部的 EPISODE_ID / DRAMA_ID / STREAM 变量来切换测试对象。
"""
import sys
import os
import asyncio

# 强制 stdout 输出 UTF-8，避免 Windows GBK 编码报错
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 路径补丁：让脚本能找到 extractor 和 comfy_api_proxy ──────────────────
_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)                                          # d:\CU
sys.path.insert(0, os.path.join(_ROOT, 'ComfyUI', 'custom_nodes')) # comfy_api_proxy 所在目录

# ── 加载 .env（千问 key 等）────────────────────────────────────────────────
from dotenv import load_dotenv  # pip install python-dotenv
load_dotenv(os.path.join(_ROOT, 'ComfyUI', 'custom_nodes', 'comfy_api_proxy', '.env'))

# ── 伪造 server 模块（ComfyUI 不在运行，routes.py 会 import server）─────────
import types
fake_server = types.ModuleType('server')

class _FakeRoutes:
    def get(self, *a, **kw): return lambda f: f
    def post(self, *a, **kw): return lambda f: f
    def put(self, *a, **kw): return lambda f: f
    def delete(self, *a, **kw): return lambda f: f

class _FakePromptServer:
    instance = None
    def __init__(self):
        self.routes = _FakeRoutes()
        self.app = types.SimpleNamespace(middlewares=[])

_FakePromptServer.instance = _FakePromptServer()
fake_server.PromptServer = _FakePromptServer
sys.modules['server'] = fake_server

# ── 现在才导入 agent（依赖上面的伪造）────────────────────────────────────
from comfy_api_proxy.agent.graph import build_agent


async def run(episode_id: int, drama_id: int, stream: bool):
    agent = build_agent(episode_id=episode_id, drama_id=drama_id)
    print(f'\n=== 开始提取 episode_id={episode_id} drama_id={drama_id} ===\n')

    if stream:
        # 流式输出，看到 agent 每一步在做什么
        async for event in agent.astream_events(
            {'messages': [('user', '请开始提取当前集的角色和场景。')]},
            version='v2',
        ):
            kind = event.get('event', '')
            name = event.get('name', '')
            if kind == 'on_tool_start':
                print(f'[工具调用] → {name}')
                inp = event.get('data', {}).get('input', {})
                if inp:
                    print(f'           输入: {str(inp)[:200]}')
            elif kind == 'on_tool_end':
                out = event.get('data', {}).get('output', '')
                if hasattr(out, 'content'):
                    out = out.content
                print(f'[工具返回] ← {name}: {str(out)[:300]}')
            elif kind == 'on_chat_model_stream':
                chunk = event.get('data', {}).get('chunk')
                if chunk and hasattr(chunk, 'content') and chunk.content:
                    print(chunk.content, end='', flush=True)
        print('\n\n=== 完成 ===')
    else:
        # 非流式，等最终结果
        result = await agent.ainvoke(
            {'messages': [('user', '请开始提取当前集的角色和场景。')]}
        )
        msgs = result.get('messages', [])
        print(msgs[-1].content if msgs else '（无输出）')


EPISODE_ID = 1
DRAMA_ID = 64
STREAM = True

if __name__ == '__main__':
    asyncio.run(run(EPISODE_ID, DRAMA_ID, stream=STREAM))
