"""
音色分配 Agent — LangGraph ReAct 实现
"""
import os
import re
import json
import logging
import pathlib
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

from .tools import VoiceTools

logger = logging.getLogger('comfy_api_proxy')

_SKILL_DIR = pathlib.Path(__file__).parent.parent / 'skills'


def _load_skill_prompt(skill_name: str) -> str:
    skill_file = _SKILL_DIR / skill_name / 'SKILL.md'
    text = skill_file.read_text(encoding='utf-8')
    text = re.sub(r'^---[\s\S]*?---\s*', '', text, count=1)
    return text.strip()


SYSTEM_PROMPT = _load_skill_prompt('voice_assigner')


def _make_voice_tools(episode_id: int) -> list:
    vt = VoiceTools(episode_id=episode_id)

    @tool
    def list_voices() -> str:
        """列出所有可用音色，包含 id、名称、性别、风格。"""
        return json.dumps(vt.list_voices(), ensure_ascii=False)

    @tool
    def get_characters() -> str:
        """获取当前集所有角色信息，包含 id、姓名、性别、年龄、性格、已分配音色。"""
        return json.dumps(vt.get_characters(), ensure_ascii=False)

    @tool
    def assign_voice(character_id: int, timbre_id: int) -> str:
        """为指定角色分配音色。character_id 为角色 ID，timbre_id 为音色 ID（来自 list_voices 返回的 id 字段）。"""
        return json.dumps(vt.assign_voice(character_id, timbre_id), ensure_ascii=False)

    return [list_voices, get_characters, assign_voice]


def build_voice_agent(episode_id: int, drama_id: int = None):
    """构建绑定了 episode_id 的音色分配 ReAct agent"""
    qwen_base_url = os.environ.get('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    qwen_api_key = os.environ.get('QWEN_API_KEY', '')
    qwen_model = os.environ.get('QWEN_MODEL', 'qwen-plus')

    llm = ChatOpenAI(
        model=qwen_model,
        base_url=qwen_base_url,
        api_key=qwen_api_key,
        temperature=0.3,
    )
    tools = _make_voice_tools(episode_id)
    return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)
