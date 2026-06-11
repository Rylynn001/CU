"""
剧本改写 Agent — LangGraph ReAct 实现
"""
import os
import re
import logging
import pathlib
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
import json
from langchain_core.tools import tool

from .tools import RewriteTools

logger = logging.getLogger('comfy_api_proxy')

_SKILL_DIR = pathlib.Path(__file__).parent.parent / 'skills'


def _load_skill_prompt(skill_name: str) -> str:
    skill_file = _SKILL_DIR / skill_name / 'SKILL.md'
    text = skill_file.read_text(encoding='utf-8')
    text = re.sub(r'^---[\s\S]*?---\s*', '', text, count=1)
    return text.strip()


SYSTEM_PROMPT = _load_skill_prompt('script_rewriter')


def _make_rewrite_tools(episode_id: int) -> list:
    rt = RewriteTools(episode_id=episode_id)

    @tool
    def read_episode_script() -> str:
        """读取当前集的原始内容，用于改写为格式化剧本。"""
        result = rt.read_episode_script()
        return json.dumps(result, ensure_ascii=False)

    @tool
    def save_script(content: str) -> str:
        """将改写后的完整剧本保存到当前集。content 为格式化剧本全文。"""
        result = rt.save_script(content)
        return json.dumps(result, ensure_ascii=False)

    return [read_episode_script, save_script]


def build_rewrite_agent(episode_id: int):
    """构建绑定了 episode_id 的剧本改写 ReAct agent"""
    qwen_base_url = os.environ.get('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    qwen_api_key = os.environ.get('QWEN_API_KEY', '')
    qwen_model = os.environ.get('QWEN_MODEL', 'qwen-plus')

    llm = ChatOpenAI(
        model=qwen_model,
        base_url=qwen_base_url,
        api_key=qwen_api_key,
        temperature=0.3,
    )
    tools = _make_rewrite_tools(episode_id)
    return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)
