#!/bin/bash
# Skills 安装脚本
# 用于安装图片和视频生成相关的 Claude Code Skills

set -e

SKILLS_DIR="${HOME}/.claude/skills"
BACKUP_DIR="${HOME}/.claude/skills_backup_$(date +%Y%m%d_%H%M%S)"

echo "================================================"
echo "  Background LangGraph Skills 安装工具"
echo "================================================"
echo ""

# 创建 skills 目录
if [ ! -d "$SKILLS_DIR" ]; then
    echo "创建 Skills 目录: $SKILLS_DIR"
    mkdir -p "$SKILLS_DIR"
else
    echo "Skills 目录已存在: $SKILLS_DIR"
fi

# 备份现有 skills（如果存在）
if [ "$(ls -A $SKILLS_DIR 2>/dev/null)" ]; then
    echo "备份现有 Skills 到: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    cp -r "$SKILLS_DIR"/* "$BACKUP_DIR"/ 2>/dev/null || true
fi

echo ""
echo "开始安装 Skills..."
echo ""

# 1. 安装 claude-image (图片生成)
echo "1️⃣  安装 claude-image (GPT Image 2 图片生成)"
if [ -d "$SKILLS_DIR/gpt-image-2" ]; then
    echo "   已存在，跳过（如需重新安装请手动删除）"
else
    echo "   克隆仓库..."
    git clone --depth 1 https://github.com/jiangmuran/claude-image.git "$SKILLS_DIR/gpt-image-2"
    echo "   ✅ claude-image 安装完成"
fi
echo ""

# 2. 安装 gemini-image-skill (Gemini 图片生成)
echo "2️⃣  安装 gemini-image-skill (Gemini 图片生成)"
if [ -d "$SKILLS_DIR/gemini-image" ]; then
    echo "   已存在，跳过"
else
    echo "   克隆仓库..."
    git clone --depth 1 https://github.com/Ceeon/gemini-image-skill.git "$SKILLS_DIR/gemini-image"
    echo "   ✅ gemini-image-skill 安装完成"
fi
echo ""

# 3. 安装 Seedance-Product-Video (视频提示词生成)
echo "3️⃣  安装 Seedance-Product-Video (视频提示词生成)"
if [ -d "$SKILLS_DIR/seedance-prompt" ]; then
    echo "   已存在，跳过"
else
    echo "   克隆仓库..."
    git clone --depth 1 https://github.com/op7418/Seedance-Product-Video.git "$SKILLS_DIR/seedance-prompt"
    echo "   ✅ Seedance-Product-Video 安装完成"
fi
echo ""

# 4. 安装 ai-media-generator (综合媒体生成)
echo "4️⃣  安装 ai-media-generator (14+ 平台综合媒体生成)"
if [ -d "$SKILLS_DIR/ai-media-generator" ]; then
    echo "   已存在，跳过"
else
    echo "   克隆仓库..."
    git clone --depth 1 https://github.com/Hao0321/ai-media-generator.git "$SKILLS_DIR/ai-media-generator"
    echo "   ✅ ai-media-generator 安装完成"
fi
echo ""

echo "================================================"
echo "  ✅ Skills 安装完成！"
echo "================================================"
echo ""
echo "已安装的 Skills:"
ls -1 "$SKILLS_DIR"
echo ""

# 配置环境变量提示
echo "⚠️  请配置必要的环境变量："
echo ""
echo "# 添加到 ~/.bashrc 或 ~/.zshrc"
echo "export OPENAI_IMAGE_API_KEY=\"sk-your-key-here\""
echo "export OPENAI_IMAGE_BASE_URL=\"https://jmrai.net/v1\"  # 可选"
echo ""
echo "# Gemini (如果使用)"
echo "export GOOGLE_API_KEY=\"your-gemini-key\""
echo ""

# 检查是否已配置
if [ -z "$OPENAI_IMAGE_API_KEY" ]; then
    echo "❌ 未检测到 OPENAI_IMAGE_API_KEY，请配置后重新加载 shell"
else
    echo "✅ OPENAI_IMAGE_API_KEY 已配置"
fi

echo ""
echo "使用方法："
echo "1. 在你的 LangGraph 工作流中引用 skill_nodes"
echo "2. 或直接在命令行测试："
echo "   python3 ~/.claude/skills/gpt-image-2/scripts/gpt_image.py generate -p \"a red panda\" -o test.png"
echo ""
echo "详细文档："
echo "  - claude-image: $SKILLS_DIR/gpt-image-2/README.md"
echo "  - Seedance: $SKILLS_DIR/seedance-prompt/README.md"
echo ""
