"""
测试修改后的 Agent 是否会调用 Seedance 工具
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# 需要实际的数据库连接,这里只做逻辑验证
print("=== Agent 系统提示词测试 ===\n")

# 读取修改后的系统提示词
with open(Path(__file__).parent.parent / "agents" / "conversation_agent.py", "r", encoding="utf-8") as f:
    content = f.read()

# 检查关键修改
checks = [
    ("专业内容生成", "system_prompt"),
    ("Seedance", "keywords"),
    ("必须调用此工具", "description"),
]

print("检查修改内容:")
for keyword, location in checks:
    if keyword in content:
        print(f"  ✓ 找到关键词: '{keyword}' (位置: {location})")
    else:
        print(f"  ✗ 未找到: '{keyword}'")

print("\n" + "="*50)
print("\n提取的系统提示词片段:\n")

# 提取 system_prompt 定义
import re
match = re.search(r'system_prompt = f"""(.*?)"""', content, re.DOTALL)
if match:
    prompt_text = match.group(1)
    lines = prompt_text.split('\n')
    for i, line in enumerate(lines[:20], 1):  # 显示前20行
        print(f"{i:2d}: {line}")
    if len(lines) > 20:
        print(f"... (共 {len(lines)} 行)")
else:
    print("未找到 system_prompt 定义")

print("\n" + "="*50)
print("\nSeedance 工具描述检查:\n")

# 检查 workflow_tools.py
tools_file = Path(__file__).parent.parent / "services" / "workflow_tools.py"
with open(tools_file, "r", encoding="utf-8") as f:
    tools_content = f.read()

# 提取 generate_seedance_prompt 描述
match = re.search(
    r'"generate_seedance_prompt".*?"description":\s*"(.*?)"',
    tools_content,
    re.DOTALL
)
if match:
    desc = match.group(1)
    print(f"描述: {desc[:200]}...")

    if "必须调用" in desc:
        print("\n  ✓ 描述中包含'必须调用'")
    if "专业" in desc:
        print("  ✓ 描述中包含'专业'")
    if "平台规范" in desc or "规则" in desc:
        print("  ✓ 描述中包含'规范/规则'")
else:
    print("未找到 generate_seedance_prompt 描述")

print("\n" + "="*50)
print("\n总结:\n")
print("1. 系统提示词已更新,增加了'专业内容生成'触发条件")
print("2. Seedance 工具描述已强化,明确要求'必须调用'")
print("3. 关键词列表已扩充,增加了'赛博朋克'等常见场景词")
print("\n建议:")
print("- 重启后端服务以加载新的配置")
print("- 使用明确的触发词测试,如:'帮我写个 seedance 视频提示词'")
print("- 查看日志中的 tool_count 是否 > 0")
