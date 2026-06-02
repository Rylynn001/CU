"""
将 ExtractTools 的 5 个方法包装成 LangGraph 可用的 tool 列表
"""
import sys
import os
import json
from langchain_core.tools import tool

# 让独立运行时能找到 extractor 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))

from extractor.tools import ExtractTools
from ..config import get_db_config


def _make_db_config() -> dict:
    import pymysql.cursors
    cfg = get_db_config()
    cfg['port'] = int(cfg.get('port', 3306))
    cfg['db'] = cfg.pop('database', cfg.get('db', ''))
    cfg['cursorclass'] = pymysql.cursors.DictCursor
    return cfg


def create_extract_tools(episode_id: int, drama_id: int) -> list:
    """
    返回绑定了 episode_id / drama_id 的 LangGraph tool 列表。
    每次 Agent 处理一集时调用一次，传入对应 ID。
    """
    et = ExtractTools(
        episode_id=episode_id,
        drama_id=drama_id,
        db_config=_make_db_config(),
    )

    @tool
    def read_script_for_extraction() -> str:
        """读取当前集的剧本正文，用于后续角色和场景提取。"""
        result = et.read_script_for_extraction()
        return json.dumps(result, ensure_ascii=False)

    @tool
    def read_existing_characters() -> str:
        """查看当前剧集项目中已有的角色，以及哪些已关联到当前集，用于去重判断。"""
        result = et.read_existing_characters()
        return json.dumps(result, ensure_ascii=False)

    @tool
    def read_existing_scenes() -> str:
        """查看当前剧集项目中已有的场景，以及哪些已关联到当前集，用于去重判断。"""
        result = et.read_existing_scenes()
        return json.dumps(result, ensure_ascii=False)

    @tool
    def save_dedup_characters(characters: str) -> str:
        """
        保存提取到的角色列表，自动去重并关联到当前集。
        参数 characters 是 JSON 字符串，格式：
        [{"name":"李明","role":"主角","appearance":"...","personality":"...","description":"..."}]
        同名角色会合并更新，不会重复创建。
        """
        data = json.loads(characters)
        result = et.save_dedup_characters(data)
        return json.dumps(result, ensure_ascii=False)

    @tool
    def save_dedup_scenes(scenes: str) -> str:
        """
        保存提取到的场景列表，自动去重并关联到当前集。
        参数 scenes 是 JSON 字符串，格式：
        [{"location":"咖啡厅","time":"下午","prompt":"cozy cafe interior, warm light"}]
        地点+时段完全相同的场景会复用，不会重复创建。
        """
        data = json.loads(scenes)
        result = et.save_dedup_scenes(data)
        return json.dumps(result, ensure_ascii=False)

    return [
        read_script_for_extraction,
        read_existing_characters,
        read_existing_scenes,
        save_dedup_characters,
        save_dedup_scenes,
    ]
