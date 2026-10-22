"""
Skill 节点 - 将外部 Skills 集成到 LangGraph 工作流
"""
import os
import logging
from typing import Dict, Any
from ..state import TaskState
from ...agents.skill_agent import SkillManager, ImageGenerationSkill, VideoPromptSkill
from ...config import settings

logger = logging.getLogger(__name__)

# 全局 Skill 管理器
skill_manager = SkillManager()


async def skill_generate_image_node(state: TaskState) -> Dict[str, Any]:
    """使用 Skill 生成图片

    从 state 中读取:
        - image_prompt: 图片提示词
        - image_size: 图片尺寸（可选，默认 1024x1024）
        - output_dir: 输出目录（可选）

    返回:
        - generated_image: 生成的图片路径
        - error: 错误信息（如果失败）
    """
    try:
        prompt = state.get("image_prompt")
        if not prompt:
            return {"error": "缺少 image_prompt 参数"}

        size = state.get("image_size", "1024x1024")
        output_dir = state.get("output_dir", settings.OUTPUT_DIR)

        # 生成输出文件名
        import uuid
        output_filename = f"skill_generated_{uuid.uuid4().hex[:8]}.png"
        output_path = os.path.join(output_dir, output_filename)

        # 使用 Skill 生成图片
        image_skill = ImageGenerationSkill(skill_manager)
        api_key = state.get("api_key")  # 从 state 中获取 API Key

        logger.info(f"使用 Skill 生成图片: {prompt[:50]}...")
        result = image_skill.generate(
            prompt=prompt,
            output_path=output_path,
            size=size,
            api_key=api_key
        )

        if result["success"]:
            logger.info(f"图片生成成功: {output_path}")
            return {"generated_image": output_path}
        else:
            error_msg = result.get("error", "未知错误")
            logger.error(f"图片生成失败: {error_msg}")
            return {"error": error_msg}

    except Exception as e:
        logger.error(f"skill_generate_image_node 异常: {e}")
        return {"error": str(e)}


async def skill_edit_image_node(state: TaskState) -> Dict[str, Any]:
    """使用 Skill 编辑图片

    从 state 中读取:
        - input_image: 输入图片路径
        - edit_instruction: 编辑指令
        - mask_image: 遮罩图片路径（可选）
        - output_dir: 输出目录（可选）

    返回:
        - edited_image: 编辑后的图片路径
        - error: 错误信息（如果失败）
    """
    try:
        input_image = state.get("input_image")
        instruction = state.get("edit_instruction")

        if not input_image or not instruction:
            return {"error": "缺少 input_image 或 edit_instruction 参数"}

        output_dir = state.get("output_dir", settings.OUTPUT_DIR)

        # 生成输出文件名
        import uuid
        output_filename = f"skill_edited_{uuid.uuid4().hex[:8]}.png"
        output_path = os.path.join(output_dir, output_filename)

        # 使用 Skill 编辑图片
        image_skill = ImageGenerationSkill(skill_manager)
        api_key = state.get("api_key")
        mask_path = state.get("mask_image")

        logger.info(f"使用 Skill 编辑图片: {instruction[:50]}...")
        result = image_skill.edit(
            input_path=input_image,
            prompt=instruction,
            output_path=output_path,
            mask_path=mask_path,
            api_key=api_key
        )

        if result["success"]:
            logger.info(f"图片编辑成功: {output_path}")
            return {"edited_image": output_path}
        else:
            error_msg = result.get("error", "未知错误")
            logger.error(f"图片编辑失败: {error_msg}")
            return {"error": error_msg}

    except Exception as e:
        logger.error(f"skill_edit_image_node 异常: {e}")
        return {"error": str(e)}


async def skill_generate_video_prompt_node(state: TaskState) -> Dict[str, Any]:
    """使用 Skill 生成视频提示词

    从 state 中读取:
        - product_name: 产品名称
        - product_description: 产品描述
        - video_style: 视频风格（A/B/C/D）
        - reference_images: 参考图片列表（可选）
        - need_voiceover: 是否需要口播（可选）

    返回:
        - video_prompt: 生成的视频提示词
        - prompt_explanation: 提示词说明（中文）
        - error: 错误信息（如果失败）
    """
    try:
        product_name = state.get("product_name")
        product_desc = state.get("product_description")

        if not product_name or not product_desc:
            return {"error": "缺少 product_name 或 product_description 参数"}

        style = state.get("video_style", "A")
        reference_images = state.get("reference_images", [])
        voiceover = state.get("need_voiceover", False)

        # 使用 Skill 生成提示词
        video_skill = VideoPromptSkill(skill_manager)

        logger.info(f"使用 Skill 生成视频提示词: {product_name}")
        result = video_skill.generate_prompt(
            product_name=product_name,
            product_description=product_desc,
            style=style,
            reference_images=reference_images,
            voiceover=voiceover
        )

        if result["success"]:
            output = result.get("output", "")
            logger.info("视频提示词生成成功")
            return {
                "video_prompt": output,
                "prompt_explanation": "视频提示词已生成（详见输出）"
            }
        else:
            error_msg = result.get("error", "未知错误")
            logger.error(f"视频提示词生成失败: {error_msg}")
            return {"error": error_msg}

    except Exception as e:
        logger.error(f"skill_generate_video_prompt_node 异常: {e}")
        return {"error": str(e)}


def get_available_skills() -> Dict[str, Dict[str, str]]:
    """获取所有可用的 Skills

    Returns:
        Skills 字典，key 为 skill name，value 为 info
    """
    return {
        skill['name']: {
            'description': skill['description'],
            'path': skill['path']
        }
        for skill in skill_manager.list_skills()
    }
