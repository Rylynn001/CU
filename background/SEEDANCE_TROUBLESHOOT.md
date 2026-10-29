# Seedance 工具调用问题诊断与解决

## 问题描述

从日志看,用户消息 "生成一个赛博朋克视频提示词" 被发送后:
- LLM 直接生成了回复
- **没有调用任何工具** (`tool_count=0`)
- 没有调用 `discover_tools`

## 根本原因

原系统提示词中只说:"需要**读取或改变后端数据时**,先调用 discover_tools"

但 Seedance 工具不是用来"改变后端数据"的,而是**辅助生成专业内容**。

模型认为用户只是在问问题,所以直接凭自己的知识回答了,没意识到需要调用专业工具。

## 已实施的修改

### 1. 系统提示词优化 (`agents/conversation_agent.py:61-71`)

**修改前**:
```python
首轮只提供了工具发现入口。需要读取或改变后端数据时，先按用户语义调用 discover_tools 寻找相关能力
```

**修改后**:
```python
**工具使用规则**：
首轮只提供了工具发现入口。当用户需要以下任何能力时，先调用 discover_tools 寻找相关工具：
1. 数据操作：读取或改变后端数据（查询模型、生成图片/视频、查询历史等）
2. 专业内容生成：需要遵循特定平台规范的提示词生成（如 Seedance/即梦视频提示词、图生视频提示词等）
3. 复杂格式转换：需要专业知识的内容转换（如分镜脚本、运镜描述等）
```

### 2. 工具描述强化 (`services/workflow_tools.py:175`)

**修改前**:
```python
"description": "生成字节跳动即梦(Seedance)平台的视频提示词。支持 2.0(15秒) 和 2.5(30秒直出,最长180秒)版本。"
```

**修改后**:
```python
"description": "生成符合字节跳动即梦(Seedance)平台规范的专业视频提示词。此工具包含完整的平台规则、时间戳分镜、运镜编码、美学约束等专业方法论。用户提到视频提示词、视频脚本、短剧、分镜等需求时必须调用此工具，不能自行生成。支持 2.0(15秒) 和 2.5(30秒直出,最长180秒)版本。"
```

### 3. 关键词扩充

新增触发关键词:
- `赛博朋克` (你的测试用例)
- `时间戳`
- `剪辑节奏`
- `视频创作`

## 测试步骤

### 1. 重启后端服务

修改后**必须重启**才能生效:

```bash
# 停止当前服务
# 然后重新启动

cd D:\CU\background
python -m uvicorn main:app --reload --port 8000
```

### 2. 测试用例

#### 测试 A: 明确提到 Seedance

**请求**:
```json
{
  "message": "帮我写一个 seedance 视频提示词，30秒赛博朋克风格",
  "session_id": null
}
```

**期望日志**:
```
对话模型开始 ... provided_tools=['discover_tools']
对话模型请求调用工具 name=discover_tools arguments={'query': '...seedance...'}
对话模型开始 ... provided_tools=['discover_tools', 'generate_seedance_prompt']
对话模型请求调用工具 name=generate_seedance_prompt arguments={...}
对话模型完成 ... tool_count=2
```

#### 测试 B: 隐含需求

**请求**:
```json
{
  "message": "生成一个30秒的赛博朋克城市夜景视频提示词",
  "session_id": null
}
```

**期望**: 因为提到"视频提示词",应该触发工具调用

#### 测试 C: 通用描述(可能不触发)

**请求**:
```json
{
  "message": "我想做一个赛博朋克风格的视频",
  "session_id": null
}
```

**情况**: 如果模型认为这是普通咨询,可能不调用工具。可以追问:"帮我生成提示词"

## 日志检查点

监控以下日志行:

1. **工具发现**:
```
对话模型请求调用工具 name=discover_tools arguments={'query': '...'}
```

2. **工具执行**:
```
对话模型请求调用工具 name=generate_seedance_prompt arguments={...}
```

3. **最终计数**:
```
对话模型完成 ... tool_count=2  ← 应该 > 0
```

## 如果仍然不调用工具

### 方案 A: 更强的描述

在 `discover_tools` 的 description 中明确列举:

```python
DISCOVER_TOOL = {
    "type": "function",
    "function": {
        "name": "discover_tools",
        "description": """根据用户当前需求，在后端能力目录中查找相关工具。

**必须调用此工具的场景**：
- 用户提到"视频提示词"、"图片提示词"、"seedance"、"即梦"
- 用户要求生成、查询、修改后端数据
- 用户要求专业格式内容(分镜、运镜、剪辑节奏等)

请用自然语言描述要完成的事，不要猜测工具名。""",
        ...
    }
}
```

### 方案 B: 用户提示优化

在前端给用户提示:

```
💡 提示：想生成专业视频提示词？试试说：
   - "帮我写一个 seedance 提示词"
   - "生成即梦平台的视频脚本"
   - "我需要一个30秒短剧的分镜"
```

### 方案 C: 预检查关键词

在 API 层加一个预处理:

```python
# api/workflow.py
async def _process_chat(...):
    # 检测关键词
    triggers = ["seedance", "即梦", "视频提示词", "分镜", "运镜"]
    if any(kw in request.message.lower() for kw in triggers):
        # 在 on_progress 中提示
        if on_progress:
            await on_progress("检测到专业内容需求，正在调用 Seedance 工具...")
```

### 方案 D: 使用 tool_choice (最强制)

强制模型先调用 discover_tools:

```python
# agents/conversation_agent.py
stream = await self.client.chat.completions.create(
    model=self.model,
    messages=messages,
    tools=request_tools,
    tool_choice={"type": "function", "function": {"name": "discover_tools"}} if turn == 0 else "auto",
    ...
)
```

## 推荐测试流程

1. ✅ **重启服务** (已修改配置)
2. ✅ **明确测试**: "帮我写一个 seedance 视频提示词"
3. ✅ **查看日志**: 确认 `tool_count > 0`
4. ⚠️ **如果还是 0**: 考虑方案 D (强制 tool_choice)

## 修改文件清单

- ✅ `agents/conversation_agent.py` - 系统提示词
- ✅ `services/workflow_tools.py` - 工具描述和关键词

**重启后生效!**
