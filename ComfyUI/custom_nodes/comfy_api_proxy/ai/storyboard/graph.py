"""
分镜拆解 Agent — LangGraph ReAct 实现
"""
import os
import re
import json
import logging
import pathlib
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

from .tools import StoryboardTools

logger = logging.getLogger('comfy_api_proxy')

_SKILL_DIR = pathlib.Path(__file__).parent.parent / 'skills'


def _load_skill_prompt(skill_name: str) -> str:
    skill_file = _SKILL_DIR / skill_name / 'SKILL.md'
    text = skill_file.read_text(encoding='utf-8')
    text = re.sub(r'^---[\s\S]*?---\s*', '', text, count=1)
    return text.strip()


SYSTEM_PROMPT = _load_skill_prompt('storyboard_breaker')


def _make_storyboard_tools(episode_id: int) -> list:
    st = StoryboardTools(episode_id=episode_id)

    @tool
    def read_storyboard_context() -> str:
        """读取剧本内容、角色列表、场景列表、已有分镜摘要，作为分镜拆解的输入上下文。"""
        return json.dumps(st.read_storyboard_context(), ensure_ascii=False)

    @tool
    def save_storyboards(storyboards: list) -> str:
        """一次性保存完整分镜列表（会先清空已有分镜）。storyboards 为分镜对象数组，每个对象包含所有镜头字段。"""
        return json.dumps(st.save_storyboards(storyboards), ensure_ascii=False)

    @tool
    def update_storyboard(storyboard_id: int, data: dict) -> str:
        """更新单个分镜的字段。storyboard_id 为分镜 ID，data 为要更新的字段字典。"""
        return json.dumps(st.update_storyboard(storyboard_id, data), ensure_ascii=False)

    return [read_storyboard_context, save_storyboards, update_storyboard]


def build_storyboard_agent(episode_id: int, drama_id: int = None):
    """构建绑定了 episode_id 的分镜拆解 ReAct agent"""
    qwen_base_url = os.environ.get('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    qwen_api_key = os.environ.get('QWEN_API_KEY', '')
    qwen_model = os.environ.get('QWEN_MODEL', 'qwen-plus')

    llm = ChatOpenAI(
        model=qwen_model,
        base_url=qwen_base_url,
        api_key=qwen_api_key,
        temperature=0.3,
    )
    tools = _make_storyboard_tools(episode_id)
    return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)
