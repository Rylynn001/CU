# Skills 集成指南

## 📚 什么是 Skills？

Skills 是基于 **SKILL.md 格式**的模块化能力包，每个 Skill 包含：
- **SKILL.md**：描述、触发条件、使用方式
- **scripts/**：实际执行脚本（通常是零依赖的 Python CLI）
- **references/**：详细参考文档（提示词技巧、API 文档、用例模板等）
- **examples/**：样例和模板

这些 Skills 最初为 Claude Code 设计，但可以被任何 Agent 系统调用。

---

## 🎯 已集成的 Skills

### 1. claude-image (GPT Image 2 图片生成)
- **Skill 名称**: `gpt-image-2`
- **功能**: 文生图、图生图、图片编辑、局部重绘
- **特点**: 
  - 支持中文文字渲染
  - 自定义分辨率（最高 3840px）
  - 精准局部编辑（`change ONLY X / preserve Y` 模式）
- **GitHub**: https://github.com/jiangmuran/claude-image

### 2. gemini-image-skill (Gemini 图片生成)
- **Skill 名称**: `gemini-image`
- **功能**: Gemini 模型的文生图和图生图
- **特点**:
  - 支持多张参考图输入
  - 质量等级控制（low/medium/high → 1K/2K/4K）
- **GitHub**: https://github.com/Ceeon/gemini-image-skill

### 3. Seedance-Product-Video (视频提示词生成)
- **Skill 名称**: `seedance-prompt`
- **功能**: 为 Seedance 2.0 生成产品宣传动画提示词
- **特点**:
  - 4 种美学风格（Apple/Microsoft/Bauhaus/Vercel）
  - 支持垫图（参考图）模式
  - 15 秒一镜到底动态影像
- **GitHub**: https://github.com/op7418/Seedance-Product-Video

### 4. ai-media-generator (综合媒体生成)
- **Skill 名称**: `ai-media-generator`
- **功能**: 支持 14+ 生成平台的图片/视频/音乐生成
- **特点**:
  - 资深导演级提示词自动生成
  - 浏览器自动执行
  - 零门槛操作
- **GitHub**: https://github.com/Hao0321/ai-media-generator

---

## 🚀 快速开始

### 安装 Skills

运行安装脚本：

```bash
cd d:\CU\background
bash scripts/install_skills.sh
```

该脚本会自动：
1. 创建 `~/.claude/skills` 目录
2. 克隆所有 Skills 到该目录
3. 备份已存在的 Skills
4. 提示配置必要的环境变量

### 配置环境变量

添加到 `~/.bashrc` 或 `~/.zshrc`：

```bash
# GPT Image 2
export OPENAI_IMAGE_API_KEY="sk-your-key-here"
export OPENAI_IMAGE_BASE_URL="https://jmrai.net/v1"  # 可选

# Gemini (如果使用)
export GOOGLE_API_KEY="your-gemini-api-key"
```

重新加载 shell：
```bash
source ~/.bashrc  # 或 source ~/.zshrc
```

---

## 💡 使用方式

### 方式一：在 LangGraph 工作流中使用

在工作流模板中添加 Skill 节点：

```python
from graph.nodes.skill_nodes import (
    skill_generate_image_node,
    skill_edit_image_node,
    skill_generate_video_prompt_node
)
from langgraph.graph import StateGraph

def create_styled_image_workflow():
    """带风格的图片生成工作流"""
    workflow = StateGraph(TaskState)
    
    # 添加 Skill 节点
    workflow.add_node("generate_image", skill_generate_image_node)
    workflow.add_node("edit_style", skill_edit_image_node)
    
    # 连接节点
    workflow.add_edge(START, "generate_image")
    workflow.add_edge("generate_image", "edit_style")
    workflow.add_edge("edit_style", END)
    
    return workflow.compile()
```

#### 节点参数说明

##### skill_generate_image_node

```python
state = {
    "image_prompt": "a red panda eating bamboo, flat vector illustration",
    "image_size": "1536x864",  # 可选，默认 1024x1024
    "output_dir": "/path/to/output",  # 可选
    "api_key": "sk-xxx"  # 可选，如已配置环境变量可省略
}

result = await skill_generate_image_node(state)
# 返回: {"generated_image": "/path/to/image.png"}
```

##### skill_edit_image_node

```python
state = {
    "input_image": "/path/to/input.png",
    "edit_instruction": "Edit the image: change ONLY the background to cyberpunk style. Preserve the character exactly.",
    "mask_image": "/path/to/mask.png",  # 可选
    "output_dir": "/path/to/output",
    "api_key": "sk-xxx"
}

result = await skill_edit_image_node(state)
# 返回: {"edited_image": "/path/to/edited.png"}
```

##### skill_generate_video_prompt_node

```python
state = {
    "product_name": "智能手表 Pro",
    "product_description": "高端智能手表，健康监测，15天续航",
    "video_style": "A",  # A=Apple, B=Microsoft, C=Bauhaus, D=Vercel
    "reference_images": ["/path/to/logo.png", "/path/to/product.png"],
    "need_voiceover": True
}

result = await skill_generate_video_prompt_node(state)
# 返回: {"video_prompt": "...", "prompt_explanation": "..."}
```

### 方式二：直接使用 Python API

```python
from agents.skill_agent import SkillManager, ImageGenerationSkill

# 初始化 Skill 管理器
skill_manager = SkillManager()

# 使用图片生成 Skill
image_skill = ImageGenerationSkill(skill_manager)

# 生成图片
result = image_skill.generate(
    prompt="a cyberpunk cityscape at night, neon lights, wide angle",
    output_path="./output/cityscape.png",
    size="1792x1024",
    quality="high"
)

if result["success"]:
    print(f"生成成功: {result['output']}")
else:
    print(f"生成失败: {result['error']}")

# 编辑图片
result = image_skill.edit(
    input_path="./input.png",
    prompt="Edit the image: change ONLY the sky to sunset colors. Preserve everything else exactly.",
    output_path="./output/edited.png"
)
```

### 方式三：命令行直接调用

每个 Skill 的脚本都可以独立运行：

```bash
# 图片生成
python3 ~/.claude/skills/gpt-image-2/scripts/gpt_image.py generate \
  -p "a red panda eating bamboo, flat vector illustration" \
  -o ./output.png \
  --size 1536x864

# 图片编辑
python3 ~/.claude/skills/gpt-image-2/scripts/gpt_image.py edit \
  -i ./input.png \
  -p "Edit: change ONLY the background to cyberpunk. Preserve subject." \
  -o ./edited.png

# 批量生成（并行）
python3 ~/.claude/skills/gpt-image-2/scripts/gpt_image.py generate \
  -p "..." \
  -n 4 \
  --concurrency 4 \
  -o ./out
# 会生成 out-1.png, out-2.png, out-3.png, out-4.png
```

---

## 🎨 实际应用场景

### 场景 1：短剧分镜生成（带风格）

```python
# 用户对话
用户: "我要做一个赛博朋克风格的短剧"

# 对话 Agent 识别参数
params = {
    "intent": "short_drama",
    "style": "cyberpunk",
    "script_path": "/path/to/script.txt",
    "scene_count": 10
}

# 工作流
1. 解析剧本 → 提取分镜描述
2. 对每个分镜:
   a. 使用 skill_generate_image_node 生成原始分镜图
   b. 使用 skill_edit_image_node 应用赛博朋克风格
   c. 调用你的 img2video API 生成视频片段
3. 拼接所有片段 → 完整短剧
```

### 场景 2：产品宣传视频

```python
# 用户对话
用户: "我要做一个产品宣传视频，产品是智能手表"

# 对话 Agent 收集信息
params = {
    "intent": "product_video",
    "product_name": "智能手表 Pro",
    "product_desc": "...",
    "style": "A",  # Apple 风格
    "reference_images": ["logo.png", "product.png"]
}

# 工作流
1. 使用 skill_generate_video_prompt_node 生成视频提示词
2. 调用 Seedance/Ark API 生成视频（使用生成的提示词）
3. 返回视频 URL
```

### 场景 3：批量生成带一致风格的角色图

```python
# 用户需求
用户: "我要生成 10 个不同姿势的角色，统一的日系动漫风格"

# 工作流
1. 生成基础角色图（skill_generate_image_node）
2. 使用基础图作为参考，生成 9 个变体：
   for pose in poses:
       skill_edit_image_node(
           input_image=base_image,
           edit_instruction=f"Change ONLY the pose to {pose}. Preserve style and character features exactly."
       )
```

---

## 📖 Skills 详细文档

每个 Skill 都有完整的文档：

- **claude-image**: `~/.claude/skills/gpt-image-2/README.md`
  - `references/prompting.md` - 提示词撰写技巧
  - `references/use-cases.md` - 10+ 种使用场景模板
  - `references/api.md` - 完整 API 参数说明
  
- **Seedance**: `~/.claude/skills/seedance-prompt/README.md`
  - `references/prompt-system.md` - 视频提示词系统规则

建议在使用前阅读对应的 README 和 references。

---

## 🛠️ 扩展和自定义

### 添加新的 Skill

1. 将 Skill 克隆到 `~/.claude/skills/<skill-name>`
2. Skill 会被自动发现（需要有 SKILL.md 文件）
3. 在 `skill_nodes.py` 中添加对应的封装函数

### 自定义 Skill 行为

可以 fork 任何 Skill 并修改：
- **提示词模板**：修改 `references/use-cases.md`
- **默认参数**：修改 `scripts/xxx.py` 中的 DEFAULT_XXX 常量
- **品牌定制**：添加你的品牌色、字体、风格到模板

---

## ⚠️ 注意事项

1. **API Key 安全**：不要将 API Key 提交到 Git
2. **环境变量**：确保在运行前正确配置环境变量
3. **并发限制**：注意各 API 的并发限制和 rate limit
4. **成本控制**：图片生成有成本，建议在工作流生成后让用户确认再执行

---

## 🔗 相关链接

- [Claude Code 官网](https://claude.com/claude-code)
- [SKILL.md 格式规范](https://github.com/anthropics/superpowers)
- [更多 Skills 库](https://github.com/agent-skills-hub/agent-skills-hub)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)

---

## 🆘 故障排查

### 问题 1：Skill 未被发现

**检查**：
```python
from agents.skill_agent import SkillManager

manager = SkillManager()
print(manager.list_skills())  # 应该列出所有已安装的 Skills
```

**解决**：确保 `~/.claude/skills/<skill-name>/SKILL.md` 存在

### 问题 2：API Key 错误

**检查**：
```bash
echo $OPENAI_IMAGE_API_KEY  # 应该输出你的 key
```

**解决**：重新配置环境变量并 `source ~/.bashrc`

### 问题 3：生成失败

**查看详细错误**：
```python
result = image_skill.generate(...)
if not result["success"]:
    print(f"错误: {result['error']}")
    print(f"输出: {result['output']}")  # 可能包含更多信息
```

---

如有问题，欢迎提 Issue 或查看各 Skill 的 GitHub 仓库。
