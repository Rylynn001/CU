"""
Seedance 视频提示词生成工具
将 seedance2.5 skill 封装为可被 langgraph 调用的工具
"""
import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class SeedancePromptTool:
    """Seedance 视频提示词生成器

    基于 seedance2.5-prompt-skill 生成即梦平台的视频提示词
    """

    # Skill 核心规则
    RULES = {
        "language": "中文",
        "version_2_0": {
            "max_duration": 15,  # 秒
            "max_refs": {"image": 9, "video": 3, "audio": 3},
            "total_refs": 12
        },
        "version_2_5": {
            "max_duration": 30,  # 秒(单次), 可延长至90s, 长视频模式180s
            "max_refs": {"image": 30, "video": 10, "audio": 10},
            "total_refs": 50
        }
    }

    # 路径选择规则
    PATHS = {
        "A": "概念驱动 (≤15s/30s 单条直出)",
        "B": "长视频流水线 (>15s/>180s 需分镜)",
        "C": "图生视频 (用户提供图片)",
        "D": "分镜板驱动 (多宫格分镜)"
    }

    def __init__(self, skill_dir: str = None):
        """初始化

        Args:
            skill_dir: seedance skill 目录路径
        """
        if skill_dir is None:
            # 默认路径
            skill_dir = Path(__file__).parent.parent.parent / "Test" / "seedance2.5提示词" / "seedance2.5-prompt-skill-main"

        self.skill_dir = Path(skill_dir)
        if not self.skill_dir.exists():
            logger.warning(f"Seedance skill 目录不存在: {self.skill_dir}")

    def determine_version(self, user_message: str) -> str:
        """判断用户使用的 Seedance 版本

        Returns:
            "2.0" 或 "2.5"
        """
        msg_lower = user_message.lower()

        # 2.5 特征词
        v25_keywords = [
            "2.5", "30秒", "90秒", "180秒", "长视频模式",
            "50个素材", "片段重拍", "绿幕", "白模",
            "时间戳编辑"
        ]

        if any(kw in msg_lower for kw in v25_keywords):
            return "2.5"

        # 2.0 特征词
        if "2.0" in msg_lower or "15秒" in msg_lower:
            return "2.0"

        # 默认 2.5(新版本)
        return "2.5"

    def determine_path(
        self,
        user_message: str,
        duration: Optional[int] = None,
        has_image: bool = False,
        has_storyboard: bool = False
    ) -> str:
        """判断生成路径

        Args:
            user_message: 用户消息
            duration: 目标时长(秒)
            has_image: 是否提供图片
            has_storyboard: 是否提供分镜板

        Returns:
            路径代码 "A"/"B"/"C"/"D"
        """
        # D: 分镜板优先
        if has_storyboard or "分镜板" in user_message or "多宫格" in user_message:
            return "D"

        # C: 图生视频
        if has_image or "图生视频" in user_message or "这张图" in user_message:
            return "C"

        # B: 长视频(需要版本判断)
        version = self.determine_version(user_message)
        threshold = 15 if version == "2.0" else 30

        if duration and duration > threshold:
            return "B"

        # A: 概念驱动(默认)
        return "A"

    def load_skill_reference(self, ref_file: str) -> str:
        """加载 skill 参考文档

        Args:
            ref_file: references/ 下的文件名

        Returns:
            文件内容
        """
        ref_path = self.skill_dir / "references" / ref_file
        if not ref_path.exists():
            logger.warning(f"参考文档不存在: {ref_path}")
            return ""

        try:
            with open(ref_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"读取参考文档失败 {ref_path}: {e}")
            return ""

    def generate_prompt_instruction(
        self,
        user_request: str,
        path: str,
        version: str = "2.5",
        duration: Optional[int] = None,
        aspect_ratio: str = "16:9",
        image_refs: List[str] = None,
        video_refs: List[str] = None
    ) -> str:
        """生成指令给 LLM,让它按 skill 规则生成提示词

        Args:
            user_request: 用户原始需求
            path: 生成路径 A/B/C/D
            version: Seedance 版本
            duration: 时长(秒)
            aspect_ratio: 比例
            image_refs: 图片引用列表
            video_refs: 视频引用列表

        Returns:
            给 LLM 的完整指令
        """
        rules = self.RULES[f"version_{version.replace('.', '_')}"]

        instruction = f"""# Seedance {version} 视频提示词生成

## 用户需求
{user_request}

## 路径选择
路径 {path}: {self.PATHS[path]}

## 参数
- 版本: Seedance {version}
- 时长: {duration or '未指定'}秒
- 比例: {aspect_ratio}
- 最大单次时长: {rules['max_duration']}秒
"""

        if image_refs:
            instruction += f"- 图片引用: {len(image_refs)}张 (最多{rules['max_refs']['image']}张)\n"
        if video_refs:
            instruction += f"- 视频引用: {len(video_refs)}个 (最多{rules['max_refs']['video']}个)\n"

        instruction += f"""
## 核心规则
1. 所有提示词必须使用中文
2. @引用格式: @图片1~@图片{rules['max_refs']['image']}, @视频1~@视频{rules['max_refs']['video']}
3. 真人脸: {"认证后可用" if version == "2.5" else "一律拦截"}
4. 台词需过版权扫描(避免歌名/片名)

## 生成要求
请根据以上信息,生成:
1. 完整的即梦平台视频提示词(中文)
2. 分镜说明(如果是路径B)
3. 首帧图建议(如果需要)
4. 注意事项

输出格式:
```
### 视频提示词
[完整提示词]

### 技术说明
- 路径: {path}
- 版本: {version}
- 时长: Xs
[其他说明]

### 首帧图建议(可选)
[首帧图描述]

### 注意事项
[审查风险/优化建议]
```
"""

        return instruction

    def extract_prompt_from_response(self, llm_response: str) -> Dict[str, Any]:
        """从 LLM 回复中提取结构化内容

        Args:
            llm_response: LLM 返回的完整文本

        Returns:
            {
                "prompt": "视频提示词",
                "first_frame_suggestion": "首帧图建议",
                "notes": "注意事项",
                "raw_response": "原始回复"
            }
        """
        lines = llm_response.split("\n")
        result = {
            "prompt": "",
            "first_frame_suggestion": "",
            "notes": "",
            "raw_response": llm_response
        }

        current_section = None
        for line in lines:
            if "### 视频提示词" in line or "##视频提示词" in line:
                current_section = "prompt"
                continue
            elif "### 首帧图建议" in line or "##首帧图建议" in line:
                current_section = "first_frame"
                continue
            elif "### 注意事项" in line or "##注意事项" in line:
                current_section = "notes"
                continue
            elif "### 技术说明" in line or "##技术说明" in line:
                current_section = "tech"
                continue

            # 跳过代码块标记
            if line.strip() in ["```", "```markdown"]:
                continue

            if current_section == "prompt":
                result["prompt"] += line + "\n"
            elif current_section == "first_frame":
                result["first_frame_suggestion"] += line + "\n"
            elif current_section == "notes":
                result["notes"] += line + "\n"

        # 清理空白
        for key in ["prompt", "first_frame_suggestion", "notes"]:
            result[key] = result[key].strip()

        return result
