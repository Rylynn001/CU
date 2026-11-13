> ## 📌 这是一个二次开发版本
>
> **上游原作：[MapleShaw/seedance2.0-prompt-skill](https://github.com/MapleShaw/seedance2.0-prompt-skill)（MIT License）**
>
> 本仓库**绝大部分内容**——SKILL.md 主体、`references/` 全部方法论文档、`experiments/` 的 30+ 实测案例、
> `projects/` 的全部创意作品——**均由原作者 [@MapleShaw](https://github.com/MapleShaw) 创作**。
> 完整 git 历史已保留，`git log` 可见原始署名。
>
> **本版本新增的部分只有一项：Seedance 2.5 支持**（详见 [下方](#-本版本新增seedance-25-支持)）。
>
> 如果你只需要 Seedance 2.0，**请直接使用[上游仓库](https://github.com/MapleShaw/seedance2.0-prompt-skill)**，那里是第一手维护。

---

<div align="center">

# Seedance Prompt Skill

**一个面向字节跳动「即梦 Seedance 2.0 / 2.5」的视频 / 图片提示词生成 Agent Skill**

让 AI Agent 帮你把「想拍什么」翻译成可直接出片的专业中文提示词。

[![Skill](https://img.shields.io/badge/Type-Agent%20Skill-6E56CF)](SKILL.md)
[![Platform](https://img.shields.io/badge/Platform-即梦%20Seedance%202.0%20|%202.5-0EA5E9)](https://jimeng.jianying.com)
[![Prompts](https://img.shields.io/badge/Prompts-中文-22C55E)]()
[![Cases](https://img.shields.io/badge/实测案例-30%2B-F59E0B)](experiments/cases)
[![Upstream](https://img.shields.io/badge/上游-MapleShaw%2Fseedance2.0--prompt--skill-8B5CF6)](https://github.com/MapleShaw/seedance2.0-prompt-skill)
[![License](https://img.shields.io/badge/License-MIT-64748B)](LICENSE)

[2.5 新增](#-本版本新增seedance-25-支持) · [快速开始](#-快速开始) · [使用示例](#-使用示例) · [文档](#-文档) · [方法论](#-方法论亮点) · [作品](#-作品展示)

</div>

---

## 简介

即梦 **Seedance** 是字节跳动的多模态 AI 视频生成模型，支持图片 / 视频 / 音频混合输入。
**2.0** 可生成 4–15 秒视频；**2.5**（2026-07-31 发布）单次直出 30 秒，平台侧可延长至 90 秒、长视频模式最长 180 秒。

但**好提示词和普通提示词，出片效果天差地别**。本项目把平台的完整能力体系、运镜 / 剪辑 / 美学方法论，以及大量真实踩坑经验，封装成一个 **Agent Skill**——接入支持 [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills) 规范的工具（如 Claude Code / Cursor）后，Agent 会在你提到视频生成时自动加载它，引导你产出可直接复制到即梦平台的方案。

> 本仓库是 **「Skill 本体 + 创意作品库 + 研发日志」三合一**——既能直接用，也完整记录了方法论从「春节手工踩坑」一路迭代成生产工具的全过程。

## 🆕 本版本新增：Seedance 2.5 支持

**这是本二次开发版本相对[上游](https://github.com/MapleShaw/seedance2.0-prompt-skill)唯一的增量。** 上游全部方法论原样继承。

### 版本路由

SKILL.md 新增「第 0 步：先判版本」。2.0 与 2.5 的分镜密度是两套写法，判错整条重写。

| 项 | 2.0 | 2.5 |
|:---|:---|:---|
| 单次时长 | 15s | **30s**（延长至 90s / 长视频模式 180s） |
| 参考素材 | 12（图9+视频3+音频3） | **50（图30+视频10+音频10）** |
| >15s 做法 | 分段生成 + 拼接 | **≤180s 无需拼接** |
| 真人脸 | 一律拦截 | **认证后可用** |
| 新能力 | — | 时间戳编辑 / 绿幕·白模参考 / 片段重拍（单秒级） |

### 方法论级变化：30 秒直出推翻了路径 B 的核心假设

> 拼接的问题是每段衔接处都有一致性损耗，人物换脸、光影跳变。
> **30 秒直出是一次推理生成的连续叙事，人物、场景、镜头语言从头到尾是同一套。这是本质区别。**

新决策树：**≤30s 单条直出 → 30–90s 平台延长 → 90–180s 长视频模式 → >180s 才回到上游那套拼接 + 剪辑公式**。

前期设计（角色卡、分镜脚本）**仍然必要**——概念不好时，直出 30 秒只是把平庸拉长了 15 秒。

### 时间戳 × 长时长 = 相乘

> 在 8 秒、十几秒的时长里写时间戳，你最多排两三个镜头，
> **30 秒配上时间戳，才第一次装得下一个完整的起承转合，这两个能力是相乘的。**

新增 30 秒时间戳分镜模板（5–6 段切分 + 全片一致性锁定句 + 全程规范收束段）与实测通过的完整范例。

### 审查规则更新

- **台词也过版权扫描**——命中常见歌名/片名会被拦（实测 `C'est la vie` 被拦，因是多首歌歌名）
- **真人脸从「禁止」改为「需认证」**——未认证人脸不支持生成，已认证可放开

### 改动清单

- 新增 [`references/seedance-2.5.md`](references/seedance-2.5.md)（216 行完整增量文档，含 6 条待验证清单）
- `SKILL.md` 15 处补丁：版本路由、核心规则分支、路径 A/B 分界、Step 2 时长档、剪辑节奏、超长视频、自检清单、CLI 限制
- 8 个 `references/` 文件加版本对照 banner，**未改动任何上游原有内容**

> ⚠️ **诚实说明**：2.5 部分基于官方发布通稿 + 三份第三方实测整理，**尚无本地 case 验证**。
> 文档中标 🔬 的条目是「看起来成立但没亲手验过」，`seedance-2.5.md` 第 7 节列了 6 条待验证清单。
> 上游那 30+ 个 case 全部是 2.0 的实测，含金量与本增量不在一个量级。

## 目录

- [本版本新增：2.5 支持](#-本版本新增seedance-25-支持)
- [核心特性](#-核心特性)
- [快速开始](#-快速开始)
- [使用示例](#-使用示例)
- [项目结构](#-项目结构)
- [文档](#-文档)
- [方法论亮点](#-方法论亮点)
- [作品展示](#-作品展示)
- [适用场景](#-适用场景)
- [贡献](#-贡献)
- [许可](#-许可)

## ✨ 核心特性

| 模块 | 解决什么 |
|:---|:---|
| 📷 **相机四维编码系统**（Z/Y/X/F） | 从「关键词记忆」升级为「坐标思维」，精准控制任何镜头 |
| 🎨 **深度美学约束** | 对标 Octane / V-Ray 渲染品质 + 6 套冷暖色调系统 + 极简先锋构图 |
| 🎬 **长视频生产流水线** | 角色卡 → 分镜 → 逐镜头的完整前期流程（含 25 格流水线） |
| ✂️ **AI 素材剪辑节奏** | 六套剪辑公式 + AI 素材首尾修剪 / 色彩统一 / 畸变遮掩对策 |
| 🖼️ **图片生成** | 角色卡片图、首帧图、关键帧图的专业提示词规范 |

**覆盖 10 大平台能力**：纯文本生成 · 一致性控制 · 运镜/动作复刻 · 创意/特效复刻 · 剧情补全 · 视频延长 · 声音控制 · 一镜到底 · 视频编辑 · 音乐卡点。

**四条生成路径**：`A` 概念驱动（2.0 ≤15s / 2.5 ≤30s）· `B` 长视频流水线（2.0 >15s / 2.5 >180s）· `C` 图生视频 · `D` 分镜板驱动。

## 🚀 快速开始

### 1. 获取

```bash
git clone <repository-url> seedance
```

### 2. 安装为 Agent Skill

将整个目录放进你所用 Agent 的 Skills 搜索路径，例如：

```bash
# Claude Code（用户级）
cp -r seedance ~/.claude/skills/seedance

# 或项目级（随仓库共享）
cp -r seedance <your-project>/.claude/skills/seedance
```

Agent 会读取 [`SKILL.md`](SKILL.md) 头部的 `description`，在你提到「即梦 / 视频提示词 / 图生视频 / 运镜 / 剪辑」等场景时**自动加载**，无需手动调用。

> 具体的 Skills 目录因工具而异，请以你使用的 Agent 工具文档为准。

### 3. 开始使用

用自然语言描述需求即可，Skill 会引导你确认时长、比例、素材，并产出 2–3 个可直接复制到即梦平台的版本。

```
帮我写一段 15 秒的赛博朋克暴雨追逐视频提示词
```

## 💡 使用示例

| 你说 | Skill 做什么 |
|:---|:---|
| 「帮我写一段 15 秒的仙侠战斗视频提示词」 | 给出 2–3 个不同风格版本 + 首帧图建议 |
| 「我有一张产品图，想做旋转展示广告，竖屏 9:16」 | 走图生视频路径，先读图分析再出提示词 |
| 「参考这个视频的运镜风格，生成城市延时摄影」 | 用多模态参考能力复刻运镜 |
| 「帮我把这段 8 秒视频延长到 15 秒」 | 给出平滑续拍的延长方案 |
| 「做一个 30 秒剧情短片，保持人物/场景不漂移」 | 走长视频流水线 + 一致性锁定 + 剪辑方案 |
| 「我想要一种压迫感的镜头，主角正面近景」 | 自动查情绪→坐标速查表返回镜头公式 |
| 「这条视频我生成了 6 条素材，该怎么剪？」 | 按六套剪辑公式推荐节奏方案 |

## 📁 项目结构

```
seedance-prompt-skill/
├── SKILL.md          # Skill 主文件（Agent 读取执行的入口）
├── README.md         # 本文件
│
├── references/       # 📚 方法论文档（Skill 运行依赖）
│   ├── platform-specs.md          # 平台参数与限制
│   ├── examples.md                # 十大能力提示词示例库
│   ├── image-generation.md        # 图片生成（角色图/首帧图）规范
│   ├── image-to-prompt.md         # 图生视频（路径 C）方法论 + 版权审查 SOP
│   ├── storyboard-driven.md       # 分镜板驱动（路径 D）方法论
│   ├── cli-integration.md         # dreamina CLI 集成（可选增值）
│   ├── creative-strategy.md       # 创意策略（≤15s 爆款模式）
│   ├── camera-codec.md            # 📷 相机四维编码系统（Z/Y/X/F）
│   ├── aesthetic-constraints.md   # 🎨 深度美学约束（渲染+色调+构图）
│   ├── production-pipeline.md     # 🎬 长视频流水线（含 25 格）
│   ├── editing-rhythm.md          # ✂️ AI 素材剪辑节奏（六套公式）
│   ├── long-video-strategy.md     # 超长视频分段生成策略
│   └── vocabulary.md              # 运镜修饰词 + 画质/大气词库
│
├── projects/         # 🎬 创意作品库（用本 Skill 产出的完整项目）
│   ├── 黑神话-封神篇/   # 3A 质感短剧 IP 全案（选角立项片 + 5 个单角色片）
│   ├── 黑神话-其他/     # 潘金莲 / 外卖员 / 打工人
│   ├── 短剧企划/        # 城市恋人 / 宠物IP短剧 / 山海战纪 / 无厘头反转段子
│   ├── 穿越万象/        # 时间 / 空间 / 维度穿越三部曲
│   ├── 概念短片/        # 太极生万物 / 时间扭曲者 / 一滴水的宇宙
│   └── 爆款实验/        # 极简爆款 / 调研爆款 / 延展创意集 / 测试清单 / 反馈延展
│
└── experiments/      # 🧪 研发与实测日志（方法论是怎么踩坑迭代出来的）
    ├── summary.md                 # 实测方法论总结（含即梦版权审查 SOP）
    ├── cases/                     # 30+ 个图生视频实测案例（含完整迭代轨迹）
    └── templates/                 # case / summary 记录模板
```

## 📚 文档

| 想做什么 | 看这里 |
|:---|:---|
| 了解 Skill 完整能力与交互流程 | [`SKILL.md`](SKILL.md) |
| 精准控制镜头（景别/角度/运动） | [`references/camera-codec.md`](references/camera-codec.md) |
| 拉到商业级 / 电影级画质 | [`references/aesthetic-constraints.md`](references/aesthetic-constraints.md) |
| 制作 >15 秒长视频 | [`references/production-pipeline.md`](references/production-pipeline.md) · [`long-video-strategy.md`](references/long-video-strategy.md) |
| 多片段剪辑节奏 | [`references/editing-rhythm.md`](references/editing-rhythm.md) |
| 用一张图生成视频（路径 C） | [`references/image-to-prompt.md`](references/image-to-prompt.md) |
| 分镜板 / 多宫格驱动（路径 D） | [`references/storyboard-driven.md`](references/storyboard-driven.md) |
| 生成角色图 / 首帧图 | [`references/image-generation.md`](references/image-generation.md) |
| 平台参数与硬限制 | [`references/platform-specs.md`](references/platform-specs.md) |
| 实测方法论怎么来的 | [`experiments/`](experiments/) |

## 🧠 方法论亮点

这套 Skill 的价值不在「提示词模板」，而在一批**实测验证过的方法论**：

- **相机四维编码（Z/Y/X/F）**：用坐标系而非零散关键词描述镜头。两条铁律——每镜头最多双轴运动；近景（Z1–Z3）+ X 轴大幅旋转 = 崩脸陷阱。14 种情绪 → 坐标速查表直接给公式。
- **史诗级画质四件套**：品质锚定开头 + 大气连贯声明 + 光影三层结构（光源→光行为→色调）+ 镜头污染增强真实感。
- **六套剪辑公式**：呼吸式 / 心跳式 / 海浪式 / 子弹时间 / 脉冲式 / 静默锤击，配 AI 素材专属五大对策。
- **极简优先铁律**：实测发现 300–500 字符的提示词常比 1800+ 字符出片更好——「过度精细的提示词反而是噪声」。
- **即梦平台内容审核 SOP**：经 8 小时 11 版二分法定位沉淀出的完整规避清单，专治提示词被平台误判。详见 [`experiments/summary.md`](experiments/summary.md)。

## 🎬 作品展示

`projects/` 收录了用本 Skill 真实产出的完整项目，例如：

- **黑神话·封神篇** — 用提示词「造」出一款不存在的 3A 大作的短剧 IP 全案（选角立项片 + 姜子牙/二郎神/妲己/闻仲/纣王 5 个单角色片）。
- **短剧企划系列** — 城市恋人、宠物 IP 短剧、山海战纪、无厘头反转段子等成片脚本。
- **穿越万象 / 概念短片** — 时间·空间·维度穿越三部曲，太极生万物、一滴水的宇宙等概念向短片。

## 🗺️ 适用场景

短剧与对白视频 · 电商产品广告 · 仙侠/奇幻/科幻大制作 · 自然风光与旅行短片 · MV / 音乐卡点 · 科普教学可视化 · 品牌宣传片。

## 🤝 贡献

欢迎提交新的实测案例、方法论改进或平台能力更新：

1. Fork 本仓库并创建分支；
2. 新案例请用 [`experiments/templates/case-template.md`](experiments/templates/case-template.md) 模板，放入 `experiments/cases/`；
3. 方法论改动请同步更新对应的 `references/` 文档；
4. 提交 Pull Request 并简述改动动机与实测效果。

## 📄 许可与署名

本项目以 [MIT License](LICENSE) 开源，**版权归原作者 [@MapleShaw](https://github.com/MapleShaw) 所有**，
LICENSE 文件原样保留、未做修改。

**归属说明**：

| 内容 | 作者 |
|:---|:---|
| SKILL.md 主体、`references/` 全部方法论、`experiments/` 30+ 实测案例、`projects/` 全部作品 | [@MapleShaw](https://github.com/MapleShaw)（[上游仓库](https://github.com/MapleShaw/seedance2.0-prompt-skill)） |
| `references/seedance-2.5.md` 及 SKILL.md / references 的 2.5 版本分支标注 | 本仓库 |

完整 git 历史已保留，`git log` 可逐条追溯原始作者署名。上游 remote 保留为 `upstream`。

**如果你只需要 Seedance 2.0，请优先使用[上游仓库](https://github.com/MapleShaw/seedance2.0-prompt-skill)。**
2.5 相关改动如果对上游有价值，欢迎原作者直接取用或合并，无需征询。

---

<div align="center">
<sub>提示词内容与方法论基于即梦 Seedance 官方能力实测整理 · 不隶属于字节跳动官方。</sub><br>
<sub>Seedance 2.0 方法论 © <a href="https://github.com/MapleShaw">MapleShaw</a> · 2.5 增量为二次开发</sub>
</div>
