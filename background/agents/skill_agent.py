"""
Skill Agent - 管理和执行外部 Skills
基于 Claude Code SKILL.md 格式
"""
import os
import json
import subprocess
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class SkillManager:
    """Skills 管理器"""

    def __init__(self, skills_dir: str = None):
        """初始化 Skill 管理器

        Args:
            skills_dir: Skills 存放目录，默认为 ~/.claude/skills
        """
        if skills_dir is None:
            skills_dir = os.path.expanduser("~/.claude/skills")
        self.skills_dir = Path(skills_dir)
        self.skills = {}
        self.load_skills()

    def load_skills(self):
        """扫描并加载所有 Skills"""
        if not self.skills_dir.exists():
            logger.warning(f"Skills 目录不存在: {self.skills_dir}")
            return

        for skill_path in self.skills_dir.iterdir():
            if not skill_path.is_dir():
                continue

            skill_md = skill_path / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                skill_info = self._parse_skill_md(skill_md)
                self.skills[skill_info['name']] = {
                    'path': skill_path,
                    'info': skill_info
                }
                logger.info(f"已加载 Skill: {skill_info['name']}")
            except Exception as e:
                logger.error(f"加载 Skill 失败 {skill_path}: {e}")

    def _parse_skill_md(self, skill_md_path: Path) -> Dict[str, Any]:
        """解析 SKILL.md 文件的 frontmatter

        Returns:
            包含 name, description, triggers, keywords 的字典
        """
        with open(skill_md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析 frontmatter（---之间的部分）
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                # 简单解析（实际项目可用 yaml 库）
                info = {}
                for line in frontmatter.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        info[key.strip()] = value.strip()
                return info

        return {'name': skill_md_path.parent.name, 'description': ''}

    def find_skill_by_intent(self, user_message: str) -> Optional[str]:
        """根据用户意图找到最匹配的 Skill

        Args:
            user_message: 用户消息

        Returns:
            匹配的 skill name，如果没有匹配返回 None
        """
        user_message_lower = user_message.lower()

        for skill_name, skill_data in self.skills.items():
            description = skill_data['info'].get('description', '').lower()
            keywords = skill_data['info'].get('keywords', '').lower()

            # 检查关键词匹配
            if any(keyword in user_message_lower for keyword in keywords.split(',')):
                return skill_name

            # 检查触发条件
            if 'trigger' in description and user_message_lower in description:
                return skill_name

        return None

    def execute_skill(
        self,
        skill_name: str,
        command: str,
        args: List[str] = None,
        env: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """执行 Skill 的脚本

        Args:
            skill_name: Skill 名称
            command: 要执行的命令（如 "generate", "edit"）
            args: 命令参数列表
            env: 环境变量

        Returns:
            执行结果 {"success": bool, "output": str, "error": str}
        """
        if skill_name not in self.skills:
            return {"success": False, "error": f"Skill 不存在: {skill_name}"}

        skill_path = self.skills[skill_name]['path']
        script_path = skill_path / "scripts"

        # 查找可执行脚本
        script_files = list(script_path.glob("*.py"))
        if not script_files:
            return {"success": False, "error": f"Skill 没有可执行脚本: {skill_name}"}

        main_script = script_files[0]  # 使用第一个找到的脚本

        # 构建命令
        cmd = ["python3", str(main_script), command]
        if args:
            cmd.extend(args)

        # 准备环境变量
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 分钟超时
                env=exec_env
            )

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "执行超时"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_skill_info(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """获取 Skill 详细信息

        Args:
            skill_name: Skill 名称

        Returns:
            Skill 信息字典，如果不存在返回 None
        """
        return self.skills.get(skill_name)

    def list_skills(self) -> List[Dict[str, str]]:
        """列出所有可用的 Skills

        Returns:
            Skills 列表，每个元素包含 name 和 description
        """
        return [
            {
                'name': name,
                'description': data['info'].get('description', ''),
                'path': str(data['path'])
            }
            for name, data in self.skills.items()
        ]


# 图片生成 Skill 封装（基于 claude-image）
class ImageGenerationSkill:
    """图片生成 Skill 封装"""

    def __init__(self, skill_manager: SkillManager):
        self.manager = skill_manager
        self.skill_name = "gpt-image-2"  # 对应 claude-image skill

    def generate(
        self,
        prompt: str,
        output_path: str,
        size: str = "1024x1024",
        quality: str = "high",
        api_key: str = None
    ) -> Dict[str, Any]:
        """生成图片

        Args:
            prompt: 提示词
            output_path: 输出文件路径
            size: 图片尺寸（如 "1536x864", "1024x1024"）
            quality: 质量（"high", "medium", "low"）
            api_key: OpenAI API Key（可选，如果已配置环境变量可不传）

        Returns:
            执行结果
        """
        args = [
            "-p", prompt,
            "-o", output_path,
            "--size", size,
            "--quality", quality
        ]

        env = {}
        if api_key:
            env["OPENAI_IMAGE_API_KEY"] = api_key

        return self.manager.execute_skill(
            self.skill_name,
            "generate",
            args=args,
            env=env
        )

    def edit(
        self,
        input_path: str,
        prompt: str,
        output_path: str,
        mask_path: str = None,
        api_key: str = None
    ) -> Dict[str, Any]:
        """编辑图片

        Args:
            input_path: 输入图片路径
            prompt: 编辑指令（使用 "change ONLY X / preserve Y" 模式）
            output_path: 输出文件路径
            mask_path: 遮罩图片路径（可选）
            api_key: OpenAI API Key

        Returns:
            执行结果
        """
        args = [
            "-i", input_path,
            "-p", prompt,
            "-o", output_path
        ]

        if mask_path:
            args.extend(["--mask", mask_path])

        env = {}
        if api_key:
            env["OPENAI_IMAGE_API_KEY"] = api_key

        return self.manager.execute_skill(
            self.skill_name,
            "edit",
            args=args,
            env=env
        )


# 视频提示词生成 Skill 封装（基于 Seedance-Product-Video）
class VideoPromptSkill:
    """视频提示词生成 Skill 封装"""

    def __init__(self, skill_manager: SkillManager):
        self.manager = skill_manager
        self.skill_name = "seedance-prompt"

    def generate_prompt(
        self,
        product_name: str,
        product_description: str,
        style: str = "A",  # A/B/C/D 对应不同美学风格
        reference_images: List[str] = None,
        voiceover: bool = False
    ) -> Dict[str, Any]:
        """生成视频提示词

        Args:
            product_name: 产品名称
            product_description: 产品描述
            style: 美学风格（A=Apple, B=Microsoft, C=Bauhaus, D=Vercel）
            reference_images: 参考图片路径列表
            voiceover: 是否需要口播

        Returns:
            生成的提示词和说明
        """
        # 构建参数
        args = [
            "--product", product_name,
            "--description", product_description,
            "--style", style
        ]

        if reference_images:
            args.extend(["--images"] + reference_images)

        if voiceover:
            args.append("--voiceover")

        return self.manager.execute_skill(
            self.skill_name,
            "generate",
            args=args
        )
