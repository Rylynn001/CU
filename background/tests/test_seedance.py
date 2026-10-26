"""
测试 Seedance 工具集成
"""
import asyncio
import sys
from pathlib import Path

# 添加 background 到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.seedance_tool import SeedancePromptTool


async def test_seedance_tool():
    """测试 Seedance 工具基本功能"""
    print("=== 测试 Seedance 工具 ===\n")

    tool = SeedancePromptTool()

    # 测试 1: 版本判断
    print("测试 1: 版本判断")
    test_messages = [
        "帮我生成一个 15 秒的视频",
        "我想做一个 30 秒的短剧",
        "用长视频模式生成 180 秒的内容"
    ]
    for msg in test_messages:
        version = tool.determine_version(msg)
        print(f"  '{msg}' -> 版本 {version}")
    print()

    # 测试 2: 路径判断
    print("测试 2: 路径判断")
    test_cases = [
        ("生成一段赛博朋克风格的追逐视频", 10, False, False),
        ("我有一张产品图，想做旋转展示", None, True, False),
        ("根据这个分镜板生成视频", None, False, True),
        ("做一个 45 秒的完整短剧", 45, False, False),
    ]
    for msg, duration, has_image, has_storyboard in test_cases:
        path = tool.determine_path(msg, duration, has_image, has_storyboard)
        print(f"  '{msg}' -> 路径 {path} ({tool.PATHS[path]})")
    print()

    # 测试 3: 生成指令
    print("测试 3: 生成指令")
    request = "帮我生成一段 30 秒的赛博朋克城市夜景视频，主角是一个穿着发光外套的女黑客"
    instruction = tool.generate_prompt_instruction(
        user_request=request,
        path="A",
        version="2.5",
        duration=30,
        aspect_ratio="16:9"
    )
    print("生成的指令(前500字符):")
    print(instruction[:500])
    print("...")
    print()

    # 测试 4: 提取提示词
    print("测试 4: 从模拟 LLM 回复中提取提示词")
    mock_response = """
### 视频提示词
30秒电影感，赛博朋克风格，霓虹灯照映的未来都市夜景。

女主角：20多岁亚裔女性黑客，黑色短发，穿着会随心跳闪烁的LED发光外套，赛博朋克护目镜推到额头上，全程保持同一套装扮和面部特征。

0-6秒：高空俯拍城市全景，紫蓝霓虹灯海，镜头缓慢下降穿过全息广告牌；
6-12秒：切到地面视角，女主角从小巷转出，LED外套闪烁蓝光，低角度跟拍；
12-19秒：快速推进到女主角正面特写，她抬头看向巨型屏幕，眼神坚定，护目镜反射代码流；
19-26秒：镜头切到她的视角，透过护目镜看到数据流和虚拟界面；
26-30秒：拉回全景，女主角转身消失在霓虹灯阴影中。

全程规范：Octane渲染质感，霓虹冷光主导（紫/蓝/青），辅以暖色光源点缀，无文字水印。

### 技术说明
- 路径: A
- 版本: 2.5
- 时长: 30s
- 比例: 16:9

### 首帧图建议
高空俯拍的赛博朋克城市夜景，密集的摩天大楼被紫蓝霓虹灯覆盖，全息广告牌飘浮在建筑间，Octane渲染质感。

### 注意事项
- 已规避真人面部(使用"亚裔女性"泛指描述)
- 无台词避免版权扫描
- 时间戳分段确保 30 秒连贯性
"""
    extracted = tool.extract_prompt_from_response(mock_response)
    print("提取的提示词(前200字符):")
    print(extracted["prompt"][:200])
    print("\n首帧图建议:")
    print(extracted["first_frame_suggestion"][:100])
    print("\n注意事项:")
    print(extracted["notes"][:100])
    print()

    print("=== 测试完成 ===")


if __name__ == "__main__":
    asyncio.run(test_seedance_tool())
