"""AI Agent 相关路由"""
import json
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import get_current_user
from config import settings
from database import execute_query

router = APIRouter()
logger = logging.getLogger(__name__)


class RewriteRequest(BaseModel):
    raw_text: str
    instruction: str


class ExtractRequest(BaseModel):
    text: str
    extraction_schema: str  # 改名避免与 BaseModel.schema 冲突


@router.post("/agent/rewrite")
async def agent_rewrite(
    req: RewriteRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    使用 AI Agent 重写剧本

    请求体:
        {
            "raw_text": "原始剧本文本",
            "instruction": "改写指令，例如：压缩到 60 秒，强化冲突"
        }

    返回:
        { "result": "重写后的剧本" }
    """
    if not settings.QWEN_API_KEY:
        raise HTTPException(status_code=500, detail='QWEN_API_KEY 未配置')

    # 构建 prompt
    system_prompt = """你是一位专业的短剧编剧。
你的任务是根据用户的改写指令，对原始剧本进行优化改写。
要求：
1. 保持故事核心和人物关系
2. 遵循用户的改写指令（时长、风格、情节等）
3. 输出完整的改写后剧本
4. 不要添加额外的说明文字，直接输出剧本内容"""

    user_prompt = f"""原始剧本：
{req.raw_text}

改写指令：
{req.instruction}

请按照指令改写剧本："""

    # 调用 Qwen API
    import httpx

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f'{settings.QWEN_BASE_URL}/chat/completions',
                headers={
                    'Authorization': f'Bearer {settings.QWEN_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': settings.QWEN_MODEL,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt}
                    ],
                    'temperature': 0.7,
                    'max_tokens': 4000
                }
            )
            resp.raise_for_status()
            data = resp.json()

            result = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            if not result:
                raise HTTPException(status_code=500, detail='AI 返回空结果')

            return {'result': result}

    except httpx.RequestError as e:
        logger.error(f'[agent-rewrite] 请求失败: {e}')
        raise HTTPException(status_code=500, detail=f'AI 请求失败: {e}')
    except Exception as e:
        logger.error(f'[agent-rewrite] 异常: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent/extract")
async def agent_extract(
    req: ExtractRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    使用 AI Agent 从文本中提取结构化信息

    请求体:
        {
            "text": "待提取的文本内容",
            "schema": "提取目标的描述，例如：提取角色列表（姓名、年龄、性格）和场景列表（名称、描述）"
        }

    返回:
        { "result": { ... } }  # JSON 对象
    """
    if not settings.QWEN_API_KEY:
        raise HTTPException(status_code=500, detail='QWEN_API_KEY 未配置')

    # 构建 prompt
    system_prompt = """你是一位专业的信息提取助手。
你的任务是从给定的文本中，按照用户指定的 schema 提取结构化信息。
要求：
1. 严格按照 schema 要求提取
2. 输出标准 JSON 格式
3. 不要添加额外的说明文字
4. 如果某些字段无法提取，使用 null 或空数组"""

    user_prompt = f"""待提取文本：
{req.text}

提取目标（schema）：
{req.extraction_schema}

请提取结构化信息，以 JSON 格式输出："""

    # 调用 Qwen API
    import httpx

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f'{settings.QWEN_BASE_URL}/chat/completions',
                headers={
                    'Authorization': f'Bearer {settings.QWEN_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': settings.QWEN_MODEL,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt}
                    ],
                    'temperature': 0.3,
                    'max_tokens': 4000,
                    'response_format': {'type': 'json_object'}
                }
            )
            resp.raise_for_status()
            data = resp.json()

            content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            if not content:
                raise HTTPException(status_code=500, detail='AI 返回空结果')

            # 尝试解析 JSON
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # 如果返回的不是纯 JSON，尝试提取 JSON 部分
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    raise HTTPException(status_code=500, detail='AI 返回的不是有效 JSON')

            return {'result': result}

    except httpx.RequestError as e:
        logger.error(f'[agent-extract] 请求失败: {e}')
        raise HTTPException(status_code=500, detail=f'AI 请求失败: {e}')
    except json.JSONDecodeError as e:
        logger.error(f'[agent-extract] JSON 解析失败: {e}')
        raise HTTPException(status_code=500, detail=f'JSON 解析失败: {e}')
    except Exception as e:
        logger.error(f'[agent-extract] 异常: {e}')
        raise HTTPException(status_code=500, detail=str(e))

