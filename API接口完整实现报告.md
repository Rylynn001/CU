# API 接口完整实现报告

生成时间: 2026-10-13

## 一、实施概览

### 1.1 完成度统计

| 模块 | 总接口数 | 已实现 | 待实现 | 完成率 |
|------|---------|--------|--------|--------|
| 用户认证 | 1 | 1 | 0 | 100% |
| API 配置与模型 | 5 | 5 | 0 | 100% |
| 图片生成 | 2 | 2 | 0 | 100% |
| 视频生成 | 2 | 2 | 0 | 100% |
| 任务管理 | 3 | 3 | 0 | 100% |
| 历史记录 | 6 | 6 | 0 | 100% |
| 资产管理 | 4 | 4 | 0 | 100% |
| 项目与分类 | 10 | 10 | 0 | 100% |
| 团队协作 | 10 | 10 | 0 | 100% |
| 节点面板 | 6 | 6 | 0 | 100% |
| Gecko 集成 | 4 | 4 | 0 | 100% |
| 短剧制作 | 23 | 23 | 0 | 100% |
| ComfyUI 直连 | 5 | 5 | 0 | 100% |
| 媒体处理 | 1 | 1 | 0 | 100% |
| **总计** | **82** | **82** | **0** | **100%** |

---

## 二、本次实现的功能

### 2.1 TTS 配音功能 (P1 优先级)

#### 实现的接口

**1. 生成角色语音样本**
```
POST /api/api-proxy/characters/{character_id}/generate-voice-sample
```

**功能说明:**
- 为角色生成试听样本音频
- 使用 MiniMax TTS API
- 自动保存到 `ai_voices` 表并更新角色的 `voice_sample_id`

**请求参数:**
```json
{
  "language": "zh",
  "text": "试听文本（可选，默认为"大家好，我是{角色名}"）"
}
```

**返回结果:**
```json
{
  "ok": true,
  "id": 123,
  "location": "/path/to/voice/xxxxx.mp3"
}
```

**实现要点:**
- 从角色的 `timbre_id` 查询音色配置
- 调用 MiniMax speech-02-turbo 模型
- 音频格式: MP3, 32kHz, 128kbps, 立体声
- 文件保存到 `settings.VOICE_DIR`
- 写入 `ai_voices` 表并关联角色

---

**2. 生成分镜配音**
```
POST /api/api-proxy/storyboards/{storyboard_id}/generate-tts
```

**功能说明:**
- 为分镜台词生成配音
- 自动解析台词中的说话人
- 使用角色的音色配置生成语音

**请求参数:**
```json
{
  "language": "zh"
}
```

**返回结果:**
```json
{
  "ok": true,
  "id": 124,
  "location": "/path/to/voice/xxxxx.mp3"
}
```

**实现要点:**
- 解析 `dialogue` 字段，支持 "角色名：台词" 和 "角色名:台词" 格式
- 查询该集中对应角色的音色配置
- 生成语音并更新分镜的 `tts_audio_id`
- 错误处理: 找不到角色或音色未分配时抛出 400

---

#### 内部实现

**核心函数: `_call_tts()`**

```python
async def _call_tts(
    voice_style: str,  # 音色 ID
    name: str,         # 角色名
    text: str,         # 文本内容
    language: str,     # 语言
    character_id: int  # 角色 ID
) -> int:  # 返回 ai_voices.id
```

**流程:**
1. 检查 `MINIMAX_API_KEY` 是否配置
2. 构建请求 payload（包含音色、音频设置）
3. 调用 MiniMax API (`/t2a_v2`)
4. 解析响应（支持二进制和 hex 两种返回格式）
5. 保存 MP3 文件到 `VOICE_DIR`
6. 写入 `ai_voices` 表，返回记录 ID

**配置要求:**
```env
MINIMAX_API_KEY=sk-xxxxx
MINIMAX_BASE_URL=https://api.vectorengine.ai/minimax/v1
```

---

### 2.2 AI Agent 功能 (P1 优先级)

#### 实现的接口

**1. Agent 重写剧本**
```
POST /api/api-proxy/agent/rewrite
```

**功能说明:**
- 使用 Qwen AI 根据指令重写剧本
- 支持时长压缩、风格调整、情节优化等

**请求参数:**
```json
{
  "raw_text": "原始剧本内容",
  "instruction": "改写指令，例如：压缩到 60 秒，强化冲突"
}
```

**返回结果:**
```json
{
  "result": "重写后的完整剧本"
}
```

**实现要点:**
- 使用 Qwen 3.5 Plus 模型
- System prompt 定义为专业短剧编剧
- Temperature: 0.7（创意生成）
- Max tokens: 4000
- 保持故事核心和人物关系不变

---

**2. Agent 提取结构化信息**
```
POST /api/api-proxy/agent/extract
```

**功能说明:**
- 从文本中提取结构化信息（角色、场景等）
- 返回标准 JSON 格式

**请求参数:**
```json
{
  "text": "待提取的文本内容",
  "schema": "提取目标描述，例如：提取角色列表（姓名、年龄、性格）和场景列表（名称、描述）"
}
```

**返回结果:**
```json
{
  "result": {
    "characters": [...],
    "scenes": [...]
  }
}
```

**实现要点:**
- 使用 Qwen 3.5 Plus 模型
- Temperature: 0.3（精确提取）
- 强制 JSON 输出模式 (`response_format: json_object`)
- 自动解析和验证 JSON 格式
- 容错处理：支持从文本中提取 JSON 块

**配置要求:**
```env
QWEN_API_KEY=sk-xxxxx
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.5-plus-2026-04-20
```

---

### 2.3 Gecko 集成功能 (P2 优先级)

**重要提醒:** 
- 这是内部系统对接，必须在生产环境测试
- Gecko API 基础地址: `https://192.168.0.25`
- 所有请求禁用 SSL 验证 (`verify=False`)
- 超时设置: 60 秒

#### 实现的接口

**1. Gecko 账号初始化**
```
POST /api/api-proxy/gecko/init
```

**功能说明:**
- 获取当前登录用户的 Gecko 账号信息
- 自动提取客户端真实 IP 地址

**返回结果:**
```json
{
  "success": true,
  "name": "用户名",
  "id": "账号ID",
  "department": "部门",
  "ip": "客户端IP"
}
```

**实现要点:**
- 优先从 `X-Forwarded-For` 头获取 IP
- 其次从 `X-Real-IP` 头获取
- 最后从 `request.client.host` 获取
- 调用 Gecko API: `/api/python-v2/get_current_account_data`
- 容错处理：未登录返回 `success: false`

---

**2. 获取任务列表**
```
POST /api/api-proxy/gecko/tasks
```

**功能说明:**
- 获取当前用户的活跃任务列表
- 支持分页查询

**请求参数:**
```json
{
  "page": 1
}
```

**返回结果:**
```json
{
  "success": true,
  "total_count": 100,
  "data_list": [
    {
      "task_id": "任务ID",
      "project_name": "项目名称",
      "task_artist": "负责人",
      "task_name": "任务名称",
      "task_type": "任务类型",
      "eps_name": "集数名称",
      "shot": "镜头"
    }
  ]
}
```

**实现要点:**
- 调用 Gecko API: `/api/python-v2/get_my_active_tasks`
- 固定参数: `page_size=50`, `task_type='shot'`, `sort='-updated_at'`
- 格式化字段名，提取关键信息

---

**3. 获取任务目录**
```
POST /api/api-proxy/gecko/task-directories
```

**功能说明:**
- 获取指定任务的目录结构信息

**请求参数:**
```json
{
  "project_name": "项目名称",
  "task_id": "任务ID",
  "task_type": "任务类型"
}
```

**返回结果:**
```json
{
  "success": true,
  "message": "目录信息"
}
```

**实现要点:**
- 调用 Gecko API: `/api/python-v2/get_task_directories`
- 直接透传 Gecko 响应

---

**4. 上传媒体文件**
```
POST /api/api-proxy/gecko/upload-media
```

**功能说明:**
- 上传媒体文件到 Gecko 任务目录
- 支持多文件上传

**请求参数 (multipart/form-data):**
- `project_name`: 项目名称
- `eps_name`: 集数名称
- `shot`: 镜头名称
- `user_name`: 用户名
- `files`: 文件列表（支持多个）

**返回结果:**
```json
{
  "success": true,
  "message": "上传成功",
  "data": {...}
}
```

**实现要点:**
- 参数映射：`eps_name` → `sequence_name`, `shot` → `shot_name`
- 所有文件字段名统一为 `files`（符合多文件上传规范）
- 调用 Gecko API: `/api/python-v2/upload_media`
- 详细日志记录：字段、文件名、大小、类型
- 容错处理：Gecko 返回失败时返回错误信息

---

## 三、文件变更清单

### 3.1 新增文件

1. **`background/api/gecko.py`**
   - Gecko 集成的完整实现
   - 包含 IP 提取、任务查询、文件上传等功能
   - 约 350 行

### 3.2 修改文件

1. **`background/api/dramas.py`**
   - 新增 `TTSRequest`, `VoiceSampleRequest` 模型
   - 新增 `generate_voice_sample()` 接口
   - 新增 `generate_storyboard_tts()` 接口
   - 新增 `_call_tts()` 内部函数
   - 新增 import: `subprocess`

2. **`background/api/agent.py`**
   - 完整实现 `agent_rewrite()` 接口
   - 完整实现 `agent_extract()` 接口
   - 新增 import: `logging`, `httpx`, `json`
   - 使用 Qwen API 替代 LangChain（更轻量）

3. **`background/main.py`**
   - 新增 `gecko` 模块导入
   - 注册 Gecko 路由: `app.include_router(gecko.router, ...)`

4. **`background/requirements.txt`**
   - 新增依赖: `httpx==0.27.0`

---

## 四、配置要求

### 4.1 环境变量 (.env)

```env
# MiniMax TTS 配置（必需）
MINIMAX_API_KEY=sk-xxxxx
MINIMAX_BASE_URL=https://api.vectorengine.ai/minimax/v1

# Qwen AI 配置（必需）
QWEN_API_KEY=sk-xxxxx
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.5-plus-2026-04-20

# 文件存储目录（确保存在并可写）
VOICE_DIR=/app/voice

# Gecko 集成（内部系统，无需配置，硬编码为 https://192.168.0.25）
```

### 4.2 数据库表要求

确保以下表存在：

1. **`ai_voices`** - 存储 TTS 生成的语音
   ```sql
   CREATE TABLE ai_voices (
       id INT AUTO_INCREMENT PRIMARY KEY,
       location VARCHAR(500),
       name VARCHAR(100),
       voice_style VARCHAR(100),
       language VARCHAR(10),
       character_id INT,
       created_at DATETIME
   );
   ```

2. **`characters`** - 角色表
   - 字段: `id`, `name`, `timbre_id`, `voice_sample_id`, `episode_id`, `deleted_at`

3. **`timbres`** - 音色配置表
   - 字段: `id`, `voice_id`

4. **`storyboards`** - 分镜表
   - 字段: `id`, `episode_id`, `dialogue`, `tts_audio_id`

5. **`episodes`** - 剧集表
   - 字段: `id`, `drama_id`, `video_url`

---

## 五、部署步骤

### 5.1 安装依赖

```bash
cd d:/CU/background
pip install -r requirements.txt
```

### 5.2 配置环境变量

编辑 `background/.env` 文件，添加必要的 API key。

### 5.3 启动服务

```bash
# 使用 Anaconda 环境
conda activate comfy311

# 启动 FastAPI 服务
cd d:/CU/background
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 5.4 验证部署

访问 API 文档: `http://localhost:8000/docs`

检查新增的接口：
- `/api-proxy/characters/{character_id}/generate-voice-sample`
- `/api-proxy/storyboards/{storyboard_id}/generate-tts`
- `/api-proxy/agent/rewrite`
- `/api-proxy/agent/extract`
- `/api-proxy/gecko/init`
- `/api-proxy/gecko/tasks`
- `/api-proxy/gecko/task-directories`
- `/api-proxy/gecko/upload-media`

---

## 六、测试建议

### 6.1 TTS 功能测试

**测试步骤:**

1. 确保有一个角色记录，并分配了 `timbre_id`
2. 调用生成语音样本接口:
   ```bash
   curl -X POST http://localhost:8000/api-proxy/characters/1/generate-voice-sample \
     -H "Content-Type: application/json" \
     -d '{"language": "zh", "text": "这是测试语音"}'
   ```
3. 检查返回的 `location` 字段
4. 验证 `ai_voices` 表中是否有新记录
5. 验证 `characters.voice_sample_id` 是否更新

**预期问题:**
- 若 MiniMax API key 无效，返回 500
- 若角色未分配音色，返回 400
- 若音频生成失败，检查 MiniMax API 响应格式

---

### 6.2 AI Agent 测试

**测试步骤:**

1. 测试剧本重写:
   ```bash
   curl -X POST http://localhost:8000/api-proxy/agent/rewrite \
     -H "Content-Type: application/json" \
     -d '{
       "raw_text": "小明和小红在公园散步。",
       "instruction": "改写成悬疑风格，60秒短剧"
     }'
   ```

2. 测试信息提取:
   ```bash
   curl -X POST http://localhost:8000/api-proxy/agent/extract \
     -H "Content-Type: application/json" \
     -d '{
       "text": "故事发生在2024年的北京。主角李华，28岁，程序员。",
       "schema": "提取时间、地点、角色（姓名、年龄、职业）"
     }'
   ```

**预期问题:**
- 若 Qwen API key 无效，返回 500
- 若 API 返回非 JSON，extract 会尝试提取 JSON 块
- 超时设置为 120 秒，长文本可能需要更长时间

---

### 6.3 Gecko 集成测试

**重要:** 必须在生产环境测试（内网可访问 `192.168.0.25`）

**测试步骤:**

1. 测试账号初始化:
   ```bash
   curl -X POST http://localhost:8000/api-proxy/gecko/init
   ```

2. 测试任务列表:
   ```bash
   curl -X POST http://localhost:8000/api-proxy/gecko/tasks \
     -H "Content-Type: application/json" \
     -d '{"page": 1}'
   ```

3. 测试文件上传:
   ```bash
   curl -X POST http://localhost:8000/api-proxy/gecko/upload-media \
     -F "project_name=测试项目" \
     -F "eps_name=EP01" \
     -F "shot=SH001" \
     -F "user_name=测试用户" \
     -F "files=@test.mp4"
   ```

**预期问题:**
- 若未登录 Gecko，init 返回 `success: false`
- 若网络不通，返回连接超时错误
- 文件上传失败时，检查 Gecko API 日志

---

## 七、已知限制

### 7.1 TTS 功能

1. **音色管理:** 需要先在 `timbres` 表中配置 MiniMax 的 `voice_id`
2. **语言支持:** 目前仅支持中文 (`zh`)，可扩展到其他语言
3. **文件存储:** 语音文件保存在本地，未集成 OSS
4. **错误重试:** 无自动重试机制，需手动重新生成

### 7.2 AI Agent 功能

1. **模型选择:** 固定使用 Qwen 3.5 Plus，可考虑提供模型选择
2. **流式输出:** 未实现 SSE 流式推送（与 ComfyUI 版本不同）
3. **上下文管理:** 无对话历史，每次调用独立
4. **提示词工程:** 提示词固定在代码中，可考虑外部配置

### 7.3 Gecko 集成

1. **API 文档依赖:** 部分接口（如 `task-directories`）可能需要根据实际 Gecko API 调整
2. **SSL 证书:** 禁用了 SSL 验证，生产环境需评估安全风险
3. **IP 识别:** 依赖反向代理正确设置 `X-Forwarded-For` 头
4. **文件大小:** 无文件大小限制，可能影响性能

---

## 八、下一步行动

### 8.1 立即部署

1. **安装依赖:** `pip install -r requirements.txt`
2. **配置环境变量:** 在 `.env` 中添加 API key
3. **启动服务:** `uvicorn main:app --host 0.0.0.0 --port 8000`
4. **验证接口:** 访问 `/docs` 查看 API 文档

### 8.2 生产测试

1. **TTS 测试:**
   - 选择一个已配置音色的角色
   - 生成语音样本
   - 验证音频质量

2. **AI Agent 测试:**
   - 测试剧本重写功能
   - 测试信息提取功能
   - 评估生成质量

3. **Gecko 测试:**
   - 在内网环境测试账号初始化
   - 测试任务列表查询
   - 测试文件上传完整流程

### 8.3 优化建议

1. **日志增强:** 添加更详细的业务日志和错误追踪
2. **监控指标:** 添加 API 调用次数、响应时间等监控
3. **配置外部化:** 将 Gecko API 地址、超时等配置移到环境变量
4. **错误处理:** 完善异常处理和用户友好的错误消息
5. **文档完善:** 编写前端调用示例和故障排查指南

---

## 九、总结

### 9.1 完成情况

✅ **P1 功能（TTS + AI Agent）:** 已完整实现
✅ **P2 功能（Gecko 集成）:** 已完整实现，待生产测试
✅ **代码质量:** 详细日志、错误处理、类型注解
✅ **文档完善:** 接口说明、配置要求、测试建议

### 9.2 交付物

1. **源代码:**
   - `background/api/gecko.py` (新增)
   - `background/api/dramas.py` (修改)
   - `background/api/agent.py` (修改)
   - `background/main.py` (修改)
   - `background/requirements.txt` (修改)

2. **文档:**
   - 本报告（完整实现说明）
   - API 接口清单（前端调用报告）

3. **部署指南:**
   - 环境配置
   - 启动命令
   - 测试步骤

### 9.3 风险提示

⚠️ **Gecko 集成:** 必须在生产环境测试，开发环境无法访问内网 API
⚠️ **API Key 安全:** 确保 `.env` 文件不被提交到版本库
⚠️ **文件存储:** 语音文件存储在本地，需定期清理或迁移到 OSS

---

**报告完成，所有 P1 和 P2 功能已实现，可直接部署到生产环境进行测试。**
