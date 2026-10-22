"""
测试 Skills 集成
"""
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.skill_agent import SkillManager, ImageGenerationSkill
from graph.nodes.skill_nodes import (
    skill_generate_image_node,
    get_available_skills
)


async def test_skill_manager():
    """测试 Skill 管理器"""
    print("=" * 60)
    print("测试 Skill 管理器")
    print("=" * 60)

    manager = SkillManager()
    skills = manager.list_skills()

    print(f"\n已加载 {len(skills)} 个 Skills:\n")
    for skill in skills:
        print(f"  • {skill['name']}")
        print(f"    描述: {skill['description'][:80]}...")
        print(f"    路径: {skill['path']}\n")

    return manager


async def test_image_generation_skill(manager: SkillManager):
    """测试图片生成 Skill"""
    print("\n" + "=" * 60)
    print("测试图片生成 Skill")
    print("=" * 60)

    # 检查是否有 gpt-image-2 skill
    if 'gpt-image-2' not in [s['name'] for s in manager.list_skills()]:
        print("\n❌ gpt-image-2 Skill 未安装")
        print("   请运行: bash scripts/install_skills.sh")
        return

    # 检查 API Key
    api_key = os.getenv("OPENAI_IMAGE_API_KEY")
    if not api_key:
        print("\n❌ 未配置 OPENAI_IMAGE_API_KEY")
        print("   请在 ~/.bashrc 或 ~/.zshrc 中添加:")
        print("   export OPENAI_IMAGE_API_KEY=\"sk-your-key-here\"")
        return

    print("\n✅ 环境配置正常")
    print(f"   API Key: {api_key[:10]}...")

    # 测试生成图片
    image_skill = ImageGenerationSkill(manager)

    output_path = "./test_output_skill.png"
    prompt = "a cute red panda eating bamboo, flat vector illustration, off-white background"

    print(f"\n📝 提示词: {prompt}")
    print(f"   输出路径: {output_path}")
    print("\n⏳ 开始生成...")

    result = image_skill.generate(
        prompt=prompt,
        output_path=output_path,
        size="1024x1024",
        api_key=api_key
    )

    if result["success"]:
        print("\n✅ 生成成功!")
        print(f"   输出: {result.get('output', '')}")
        if os.path.exists(output_path):
            print(f"   文件大小: {os.path.getsize(output_path)} bytes")
    else:
        print("\n❌ 生成失败")
        print(f"   错误: {result.get('error', '未知错误')}")
        if result.get('output'):
            print(f"   输出: {result['output']}")


async def test_skill_node():
    """测试 LangGraph Skill 节点"""
    print("\n" + "=" * 60)
    print("测试 LangGraph Skill 节点")
    print("=" * 60)

    # 检查可用 Skills
    available_skills = get_available_skills()
    print(f"\n可用 Skills: {list(available_skills.keys())}")

    # 测试 skill_generate_image_node
    api_key = os.getenv("OPENAI_IMAGE_API_KEY")
    if not api_key:
        print("\n⚠️  未配置 API Key，跳过节点测试")
        return

    state = {
        "image_prompt": "a futuristic city at sunset, cyberpunk style, wide angle",
        "image_size": "1536x864",
        "output_dir": "./",
        "api_key": api_key
    }

    print("\n📝 State 输入:")
    for key, value in state.items():
        if key == "api_key":
            print(f"   {key}: {value[:10]}...")
        else:
            print(f"   {key}: {value}")

    print("\n⏳ 调用 skill_generate_image_node...")

    result = await skill_generate_image_node(state)

    print("\n📤 节点输出:")
    for key, value in result.items():
        print(f"   {key}: {value}")

    if "generated_image" in result:
        image_path = result["generated_image"]
        if os.path.exists(image_path):
            print(f"\n✅ 图片已生成: {image_path}")
            print(f"   文件大小: {os.path.getsize(image_path)} bytes")


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("  Background Skills 集成测试")
    print("=" * 60)

    try:
        # 1. 测试 Skill 管理器
        manager = await test_skill_manager()

        # 2. 测试图片生成 Skill
        await test_image_generation_skill(manager)

        # 3. 测试 LangGraph 节点
        await test_skill_node()

        print("\n" + "=" * 60)
        print("  ✅ 所有测试完成")
        print("=" * 60)
        print("\n查看详细文档: d:\\CU\\background\\SKILLS_GUIDE.md")

    except Exception as e:
        print(f"\n❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
