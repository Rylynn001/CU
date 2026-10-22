# LangGraph 对话式工作流 - 第一阶段完成

## 已完成功能

### 1. 基础架构搭建 ✅
- [x] 添加 LangGraph 依赖到 `requirements.txt`
- [x] 创建目录结构（`agents/`, `graph/`, `graph/nodes/`, `graph/templates/`）
- [x] 定义状态类型（`ConversationState`, `TaskState`）

### 2. 对话管理 Agent ✅
- [x] 意图识别（`understand_intent`）
  - 支持识别：短剧制作、批量生图、单个视频生成、图生视频
- [x] 参数提取（`extract_parameters`）
  - 从对话历史中智能提取结构化参数
- [x] 缺失参数询问（`generate_question`）
  - 主动追问缺失的必填参数
- [x] 参数验证（`validate_parameters`）
  - 验证参数合理性（数量范围、模型有效性等）

### 3. 数据库 ✅
- [x] 创建 4 张新表
  - `workflow_sessions` - 工作流会话
  - `workflow_conversations` - 对话记录
  - `workflow_executions` - 工作流执行记录
  - `workflow_reviews` - 审核任务
- [x] Repository 层（`workflow_repo.py`）
  - 会话管理（创建、查询、更新）
  - 对话记录管理
  - 执行记录管理
  - 审核任务管理

### 4. API 接口 ✅
- [x] `POST /api-proxy/workflow/chat` - 对话接口
  - 支持新建会话或继续已有会话
  - 多轮对话状态保持
  - 参数收集完成后返回 `workflow_ready: true`
- [x] `GET /api-proxy/workflow/sessions` - 获取用户会话列表
- [x] `GET /api-proxy/workflow/sessions/{id}` - 获取会话详情

### 5. 集成到主应用 ✅
- [x] 注册路由到 `main.py`
- [x] JWT 认证集成（复用现有 `get_current_user`）

---

## 使用示例

### 启动服务
```bash
cd d:/CU/background
D:/Software/anaconda3/envs/comfy311/python.exe main.py
```

### API 调用示例

#### 1. 登录获取 Token
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# 响应
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer"
}
```

#### 2. 开始对话
```bash
TOKEN="your_token_here"

# 第一轮
curl -X POST http://localhost:8000/api-proxy/workflow/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "我要做一个短剧"}'

# 响应
{
  "reply": "好的，请问你有现成的剧本吗？还是需要我帮你生成？",
  "session_id": "uuid-xxx",
  "intent": "short_drama",
  "parameters": {},
  "workflow_ready": false
}
```

#### 3. 继续对话
```bash
curl -X POST http://localhost:8000/api-proxy/workflow/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "我有剧本，在 /path/to/script.txt",
    "session_id": "uuid-xxx"
  }'

# 响应
{
  "reply": "需要生成多少个分镜？",
  "session_id": "uuid-xxx",
  "intent": "short_drama",
  "parameters": {
    "script_path_or_content": "/path/to/script.txt"
  },
  "workflow_ready": false
}
```

#### 4. 完成参数收集
```bash
# 继续回答问题，直到所有必填参数收集完成
# 最终响应
{
  "reply": "好的，参数已收集完成。准备为你生成【短剧制作】工作流...",
  "session_id": "uuid-xxx",
  "intent": "short_drama",
  "parameters": {
    "script_path_or_content": "/path/to/script.txt",
    "shot_count": 10,
    "video_duration": 5,
    "model": "ark"
  },
  "workflow_ready": true
}
```

#### 5. 查看会话详情
```bash
curl http://localhost:8000/api-proxy/workflow/sessions/uuid-xxx \
  -H "Authorization: Bearer $TOKEN"

# 响应
{
  "id": "uuid-xxx",
  "intent": "short_drama",
  "parameters": {...},
  "status": "ready",
  "conversations": [
    {"role": "user", "message": "我要做一个短剧", "created_at": "..."},
    {"role": "agent", "message": "好的，请问...", "created_at": "..."},
    ...
  ]
}
```

---

## 测试脚本

### 方式一：直接测试 Agent（不需要服务）
```bash
cd d:/CU/background
D:/Software/anaconda3/envs/comfy311/python.exe test_conversation.py
```

### 方式二：测试完整 API（需要先启动服务）
```bash
# 确保服务已启动
D:/Software/anaconda3/envs/comfy311/python.exe test_workflow_api.py
```

---

## 数据库迁移

如果需要在新环境初始化数据库：
```bash
cd d:/CU/background
D:/Software/anaconda3/envs/comfy311/python.exe init_workflow_db.py
```

查看已创建的表：
```sql
SHOW TABLES LIKE 'workflow_%';

-- 输出：
-- workflow_sessions
-- workflow_conversations
-- workflow_executions
-- workflow_reviews
```

---

## 环境变量

确保 `.env` 文件包含以下配置：
```env
# OpenAI API（用于 LLM 调用）
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1  # 或其他兼容端点

# 数据库
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=...
DB_NAME=cu_database
```

---

## 下一步计划

### 第二阶段：工作流生成与执行（预计 1-2 周）
- [ ] 工作流模板库（短剧、批量生图等）
- [ ] 动态工作流生成器
- [ ] 成本估算器
- [ ] 工作流执行引擎
- [ ] 人工审核节点

### 第三阶段：前端集成（预计 1-2 周）
- [ ] Vue 聊天界面
- [ ] 工作流可视化
- [ ] 审核界面

---

## 技术架构

```
用户 → 对话 Agent → 参数收集 → 工作流生成 → 工作流执行 → 结果返回
       ↓
    [意图识别] → [参数提取] → [参数验证]
       ↓
    [多轮追问]
       ↓
    [workflow_ready: true]
       ↓
    [触发工作流生成]（第二阶段）
```

---

## 故障排查

### 服务无法启动
检查日志：
```bash
tail -f d:/CU/background/logs/server_*.log
```

### 对话 Agent 无响应
1. 检查 `OPENAI_API_KEY` 是否正确
2. 检查网络连接
3. 查看错误日志

### 数据库连接失败
1. 确认 MySQL 服务运行中
2. 检查 `.env` 数据库配置
3. 验证数据库用户权限

---

## 贡献者
- 对话 Agent 核心逻辑
- 数据库 Schema 设计
- API 接口实现

---

## License
MIT
