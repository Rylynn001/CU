# Seedance 工具集成说明

## 概述

已将 seedance2.5 提示词技能集成到 langgraph 对话系统中。用户可以通过聊天界面生成即梦(Seedance)平台的专业视频提示词。

## 工作原理

### 1. 工具注册

在 `WorkflowTools` 中注册了新工具 `generate_seedance_prompt`:

```python
"generate_seedance_prompt": {
    "type": "function",
    "function": {
        "name": "generate_seedance_prompt",
        "description": "生成字节跳动即梦(Seedance)平台的视频提示词。支持 2.0(15秒) 和 2.5(30秒直出,最长180秒)版本。",
        "parameters": {
            "type": "object",
            "properties": {
                "request": {"type": "string", "description": "用户的视频创意需求描述"},
                "version": {"type": "string", "enum": ["2.0", "2.5"], "default": "2.5"},
                "duration": {"type": "integer", "minimum": 4, "maximum": 180},
                "aspect_ratio": {"type": "string", "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"]},
            },
            "required": ["request"],
        },
    },
    "keywords": [
        "seedance", "即梦", "视频提示词", "短剧", "视频生成", "AI视频",
        "小云雀", "豆包", "30秒视频", "长视频", "视频脚本",
        "运镜", "镜头", "分镜", "剪辑", "图生视频"
    ],
}
```

### 2. 触发机制

当用户消息包含以下关键词时,LLM 会自动发现并调用此工具:
- seedance, 即梦, 视频提示词, 短剧, 视频生成
- 运镜, 镜头, 分镜, 剪辑
- 30秒视频, 长视频, 图生视频

### 3. 处理流程

```
用户消息
  ↓
LLM 通过 discover_tools 查找工具
  ↓
调用 generate_seedance_prompt
  ↓
SeedancePromptTool 生成指令
  ↓
LLM 根据指令生成符合 Seedance 规则的提示词
  ↓
返回给用户
```

### 4. 路径自动判断

工具会根据用户需求自动选择生成路径:

| 路径 | 适用场景 | 触发条件 |
|-----|---------|---------|
| A | 概念驱动 | ≤15s(2.0) 或 ≤30s(2.5) 的单条视频 |
| B | 长视频流水线 | >15s(2.0) 或 >180s(2.5) 需要分镜 |
| C | 图生视频 | 用户提供图片或提到"图生视频" |
| D | 分镜板驱动 | 用户提供分镜板或多宫格 |

### 5. 版本判断

- 默认使用 **Seedance 2.5**(30秒直出)
- 若用户明确提到 "2.0" 或 "15秒",则使用 2.0
- 若提到 "30秒"、"长视频模式"、"180秒" 等,确认使用 2.5

## 使用示例

### 示例 1: 基础视频生成

**用户**: 帮我生成一段 30 秒的赛博朋克城市夜景视频

**系统响应**:
1. LLM 发现需要 seedance 工具
2. 调用 `generate_seedance_prompt`
3. 自动判断:
   - 版本: 2.5
   - 路径: A (概念驱动)
   - 时长: 30秒
4. 返回完整的中文视频提示词,包含:
   - 时间戳分镜(0-6秒、6-12秒...)
   - 运镜描述
   - 美学约束
   - 首帧图建议

### 示例 2: 图生视频

**用户**: 我有一张产品图,想做成旋转展示的广告视频

**系统响应**:
1. 判断为路径 C(图生视频)
2. 生成提示词时:
   - 使用 `@图片1` 引用
   - 控制字符数在 300-500 范围
   - 补充时长、运镜、节奏

### 示例 3: 长视频

**用户**: 做一个 60 秒的完整短剧,有起承转合

**系统响应**:
1. 版本: 2.5
2. 路径: B (长视频流水线)
3. 生成:
   - 角色卡建议
   - 分镜脚本
   - 逐镜头提示词
   - 剪辑节奏建议

## 核心规则(已内置)

工具已封装以下 Seedance 规则:

1. **所有提示词必须中文**
2. **@引用格式**:
   - 2.0: @图片1~9, @视频1~3, @音频1~3
   - 2.5: @图片1~30, @视频1~10, @音频1~10
3. **真人脸规则**:
   - 2.0: 一律拦截
   - 2.5: 认证后可用
4. **台词版权扫描**: 避免使用歌名、片名
5. **时长限制**:
   - 2.0: 单次 15秒
   - 2.5: 单次 30秒, 可延长至90秒, 长视频模式180秒

## 文件结构

```
background/
├── services/
│   ├── seedance_tool.py          # Seedance 工具核心
│   └── workflow_tools.py         # 工具注册和集成
├── tests/
│   └── test_seedance.py          # 测试脚本
└── ...
```

## 测试

运行测试脚本:

```bash
cd D:\CU\background
python tests/test_seedance.py
```

测试覆盖:
- ✅ 版本判断(2.0 vs 2.5)
- ✅ 路径判断(A/B/C/D)
- ✅ 指令生成
- ✅ 提示词提取

## API 调用示例

通过 `/api/api-proxy/workflow/chat/stream` 发送:

```json
{
  "message": "帮我生成一个 30 秒的赛博朋克视频提示词,主角是女黑客",
  "session_id": "session_xxx"
}
```

系统会:
1. 自动调用 `generate_seedance_prompt`
2. 生成符合即梦平台规范的提示词
3. 通过 SSE 流式返回

## 下一步优化

### 当前状态
- ✅ 基础工具集成完成
- ✅ 版本和路径自动判断
- ✅ 核心规则封装

### 可选增强
1. **读取完整 skill 文档**: 目前工具只封装了核心逻辑,可以进一步读取 `references/` 下的方法论文档
2. **参考素材支持**: 支持用户上传图片/视频作为参考
3. **案例库**: 接入 `experiments/cases/` 中的 30+ 实测案例
4. **直接调用 dreamina CLI**: 从提示词生成到实际视频输出的完整流程

## 注意事项

1. **skill 目录位置**: 默认期望 seedance skill 在 `D:\CU\Test\seedance2.5提示词\seedance2.5-prompt-skill-main`,如需修改请更新 `SeedancePromptTool.__init__` 中的路径

2. **LLM 生成质量**: 工具只负责提供规则和指令,最终提示词质量取决于对话模型(GPT-4/Claude/等)的理解和生成能力

3. **中文编码**: 测试输出有中文乱码是终端编码问题,实际 API 返回的 JSON 是正确的 UTF-8

4. **版权审查**: 工具已内置基本规则,但用户仍需注意:
   - 避免真人脸(2.0)
   - 台词不使用歌名/片名
   - 参考素材的版权合规

## 参考

- Seedance 2.5 文档: `Test/seedance2.5提示词/seedance2.5-prompt-skill-main/SKILL.md`
- 上游项目: https://github.com/MapleShaw/seedance2.0-prompt-skill
