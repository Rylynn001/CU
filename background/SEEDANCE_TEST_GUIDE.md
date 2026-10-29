# Seedance 工具集成 - 最终测试指南

## ✅ 已完成的增强

### 1. 系统提示词优化
- 新增"专业内容生成"作为工具调用触发条件
- 明确列举 Seedance/视频提示词为需要工具的场景

### 2. 工具描述强化  
- 描述中明确"必须调用此工具"
- 强调"包含完整平台规则、方法论"
- 扩充关键词:赛博朋克、时间戳、剪辑节奏等

### 3. **关键词强制触发**(新增)
当用户消息包含以下关键词时,**强制调用 discover_tools**:
- `seedance`
- `即梦`  
- `视频提示词`
- `视频脚本`
- `分镜`
- `运镜`
- `剪辑节奏`
- `时间戳`

实现位置: `agents/conversation_agent.py:89-107`

## 🚀 测试步骤

### 1. 重启服务

**必须重启**才能加载新配置:

```bash
# 停止当前运行的服务
Ctrl+C

# 重新启动
cd D:\CU\background
python -m uvicorn main:app --reload --port 8000
```

### 2. 测试用例

#### 测试 1: 明确 Seedance (必定触发)

**请求**:
```bash
curl -X POST http://localhost:8000/api-proxy/workflow/chat/stream \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我写一个 seedance 视频提示词，30秒赛博朋克风格"
  }'
```

**期望日志**:
```
检测到专业内容关键词，强制调用 discover_tools request_id=xxx keywords=['seedance', '视频提示词']
对话模型开始 ... provided_tools=['discover_tools']
对话模型请求调用工具 name=discover_tools
对话模型开始 ... provided_tools=['discover_tools', 'generate_seedance_prompt']
对话模型请求调用工具 name=generate_seedance_prompt
对话模型完成 ... tool_count=2 ✓
```

#### 测试 2: 隐含关键词 (应该触发)

**请求**:
```json
{
  "message": "生成一个30秒赛博朋克视频的分镜脚本"
}
```

**触发词**: `分镜`

**期望**: 强制调用 discover_tools → 发现 seedance 工具 → 生成提示词

#### 测试 3: 原问题复现 (现在应该触发)

**请求**:
```json
{
  "message": "生成一个赛博朋克视频提示词"  
}
```

**触发词**: `视频提示词`

**期望**: 
```
检测到专业内容关键词，强制调用 discover_tools ... keywords=['视频提示词']
...
tool_count=2 ✓
```

#### 测试 4: 普通咨询 (不应触发)

**请求**:
```json
{
  "message": "赛博朋克是什么风格？"
}
```

**预期**: 直接回答,不调用工具 (tool_count=0 是正确的)

## 📊 日志关键点

### 成功调用的日志特征:

```
# 1. 关键词检测
检测到专业内容关键词，强制调用 discover_tools request_id=8a2a733e keywords=['seedance']

# 2. 第一轮:discover
对话模型开始 request_id=8a2a733e ... round=0 provided_tools=['discover_tools']
对话模型请求调用工具 name=discover_tools arguments={'query': '生成seedance视频提示词'}

# 3. 第二轮:调用实际工具
对话模型开始 request_id=8a2a733e ... round=1 provided_tools=['discover_tools', 'generate_seedance_prompt']
对话模型请求调用工具 name=generate_seedance_prompt arguments={...}

# 4. 最终结果
对话模型完成 request_id=8a2a733e ... tool_count=2 ✓
```

### 失败的日志特征:

```
# 直接回答,没有关键词检测行
对话模型开始 request_id=8a2a733e ... round=0 provided_tools=['discover_tools']
对话模型完成 request_id=8a2a733e ... tool_count=0 ✗
```

## 🔧 如果还是不调用

### 检查 1: 确认修改生效

```bash
grep -n "检测到专业内容关键词" D:\CU\background\agents\conversation_agent.py
# 应该返回行号

grep -n "force_tool_choice" D:\CU\background\agents\conversation_agent.py  
# 应该看到在 create() 调用中使用
```

### 检查 2: 测试关键词检测逻辑

```python
# 在 Python 环境中测试
message = "帮我写一个 seedance 视频提示词"
message_lower = message.lower()
keywords = ["seedance", "即梦", "视频提示词", "视频脚本"]
matched = [kw for kw in keywords if kw in message_lower]
print(f"匹配的关键词: {matched}")  # 应该输出: ['seedance', '视频提示词']
```

### 检查 3: 模型配置

确认使用的模型支持 `tool_choice` 参数:
- ✅ GPT-4, GPT-3.5-turbo
- ✅ Claude (通过 OpenAI 兼容层)
- ❌ 某些国产模型可能不支持

如果不支持,可以回退修改或联系模型提供商。

## 📝 修改的文件

```
background/
├── agents/
│   └── conversation_agent.py      # ✓ 系统提示词 + 关键词强制触发
├── services/
│   └── workflow_tools.py          # ✓ 工具描述强化 + 关键词扩充
└── SEEDANCE_TROUBLESHOOT.md       # ✓ 诊断文档
```

## 🎯 期望结果

测试消息: **"生成一个赛博朋克视频提示词"**

**之前**:
- ❌ tool_count=0
- ❌ 直接回答

**修改后**:
- ✅ 检测到关键词:`视频提示词`
- ✅ 强制调用 discover_tools
- ✅ 发现并调用 generate_seedance_prompt
- ✅ tool_count=2
- ✅ 返回符合 Seedance 规范的专业提示词

## 💡 使用建议

用户可以用多种方式触发:

**明确指定**:
- "帮我写一个 seedance 提示词"
- "用即梦平台生成视频"

**隐含触发**:
- "生成视频提示词"(包含`视频提示词`)
- "写个30秒的分镜脚本"(包含`分镜`)
- "这个视频的运镜怎么设计"(包含`运镜`)

**不会触发** (正常):
- "什么是赛博朋克?"(纯咨询)
- "推荐一些视频网站"(无关)

---

**重启服务后即可测试!**
