"""
角色/场景提取 Agent — LangGraph ReAct 实现
使用千问大模型（通义千问，兼容 OpenAI 接口）

用法：
    from .graph import run_extractor_agent
    result = await run_extractor_agent(episode_id=1, drama_id=1)
"""
import os
import re
import logging
import pathlib
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from .tools import create_extract_tools

logger = logging.getLogger('comfy_api_proxy')

_QWEN_BASE_URL = os.environ.get('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
_QWEN_API_KEY  = os.environ.get('QWEN_API_KEY', '')
_QWEN_MODEL    = os.environ.get('QWEN_MODEL', 'qwen-plus')

_SKILL_DIR = pathlib.Path(__file__).parent / 'skills'


def _load_skill_prompt(skill_name: str) -> str:
    """读取 skills/<skill_name>/SKILL.md，去掉 frontmatter 后作为 system prompt 返回。"""
    skill_file = _SKILL_DIR / skill_name / 'SKILL.md'
    text = skill_file.read_text(encoding='utf-8')
    text = re.sub(r'^---[\s\S]*?---\s*', '', text, count=1)
    return text.strip()


SYSTEM_PROMPT = _load_skill_prompt('extractor')

def build_agent(episode_id: int, drama_id: int):
    """构建绑定了 episode_id/drama_id 的 ReAct agent"""
    llm = ChatOpenAI(
        model=_QWEN_MODEL,
        base_url=_QWEN_BASE_URL,
        api_key=_QWEN_API_KEY,
        temperature=0.2,
    )
    tools = create_extract_tools(episode_id=episode_id, drama_id=drama_id)
    return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)


async def run_extractor_agent(episode_id: int, drama_id: int) -> dict:
    """非流式运行，返回最终消息。适合测试用。"""
    agent = build_agent(episode_id, drama_id)
    logger.info(f'[extractor-agent] 开始提取 episode_id={episode_id} drama_id={drama_id}')

    result = await agent.ainvoke({
        'messages': [('user', '请开始提取当前集的角色和场景。')]
    })

    messages = result.get('messages', [])
    last = messages[-1].content if messages else ''
    logger.info(f'[extractor-agent] 完成 episode_id={episode_id}, 最终消息: {last[:100]}')
    return {'messages': [m.content for m in messages], 'summary': last}
