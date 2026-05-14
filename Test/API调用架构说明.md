# ComfyUI API Proxy 多线程调用架构说明

## 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           前端 (Vue.js)                                  │
│  ┌──────────────┐                              ┌──────────────┐         │
│  │ 图片生成页面  │                              │ 视频生成页面  │         │
│  │ TextToImage  │                              │ TextToVideo  │         │
│  └──────┬───────┘                              └──────┬───────┘         │
│         │                                             │                 │
│         │ POST /api-proxy/txt2img                    │ POST /api-proxy/txt2video
│         │ { model: 1, prompt: "..." }                │ { model: 2, prompt: "..." }
└─────────┼─────────────────────────────────────────────┼─────────────────┘
          │                                             │
          ▼                                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    ComfyUI Backend (Python aiohttp)                      │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │                    routes.py (异步路由)                         │    │
│  │                                                                 │    │
│  │  @routes.post('/api-proxy/txt2img')                            │    │
│  │  async def txt2img(request):                                   │    │
│  │      1. 接收 model ID (主键)                                    │    │
│  │      2. 查询数据库获取 model.name 和 model.rfid                 │    │
│  │      3. 通过 rfid 查询 provider 的 url 和 key                   │    │
│  │      4. 根据 model.name 判断调用哪种 API                        │    │
│  │                                                                 │    │
│  │      ┌─────────────────────────────────────────────────┐       │    │
│  │      │  模型类型判断 (_detect_model_provider)           │       │    │
│  │      │                                                  │       │    │
│  │      │  • 'openai'  → DALL-E, GPT 系列                 │       │    │
│  │      │  • 'gemini'  → Gemini 系列                       │       │    │
│  │      │  • 'generic' → 其他模型（通用异步 API）          │       │    │
│  │      └─────────────────────────────────────────────────┘       │    │
│  │                                                                 │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────┬──────────────────┬──────────────────────────────┐   │
│  │              │                  │                              │   │
│  ▼              ▼                  ▼                              ▼   │
│ ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│ │ OpenAI   │  │ Gemini   │  │ Redis 队列    │  │ 通用异步 API      │  │
│ │ 直接调用  │  │ 线程池    │  │ (Gemini图片)  │  │ (其他模型)        │  │
│ └──────────┘  └──────────┘  └──────────────┘  └──────────────────┘  │
│      │              │              │                    │             │
│      │              │              │                    │             │
└──────┼──────────────┼──────────────┼────────────────────┼─────────────┘
       │              │              │                    │
       ▼              ▼              ▼                    ▼
```

## 三种调用模式详解

### 模式 1: OpenAI SDK 直接调用 (同步转异步)

```python
# 使用场景：DALL-E 模型
if provider == 'openai':
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await client.images.generate(
        model=model_name,
        prompt=prompt,
        size="1024x1024",
        n=1,
    )
    # 直接返回结果
    return web.json_response({'images': [{'url': img.url} for img in response.data]})
```

**流程图：**
```
前端请求 → aiohttp 异步处理 → AsyncOpenAI SDK → 上游 API
                                      ↓
                                  等待响应
                                      ↓
                              直接返回结果给前端
```

**特点：**
- ✅ 使用 AsyncOpenAI，天然支持异步
- ✅ 不阻塞事件循环
- ✅ 直接返回结果，无需轮询

---

### 模式 2: Gemini SDK + 线程池 (同步 SDK 转异步)

```python
# 使用场景：Gemini 视频生成 (Veo)
elif provider == 'gemini':
    # 定义同步函数（因为 Gemini SDK 是同步的）
    def _generate_gemini_video():
        client = genai.Client(...)
        operation = client.models.generate_videos(...)
        # 轮询等待完成（最多 5 分钟）
        for _ in range(30):
            if operation.done:
                break
            time.sleep(10)  # 同步阻塞
            operation = client.operations.get(operation)
        return video_urls
    
    # 在线程池中运行同步函数
    loop = asyncio.get_event_loop()
    video_urls = await loop.run_in_executor(_executor, _generate_gemini_video)
    return web.json_response({'video_url': video_urls[0]})
```

**流程图：**
```
前端请求 → aiohttp 异步处理
              ↓
         提交到线程池 (_executor)
              ↓
    ┌─────────────────────────┐
    │  工作线程 (ThreadPool)   │
    │                         │
    │  同步调用 Gemini SDK     │
    │  time.sleep(10) 轮询    │  ← 阻塞在这个线程，不影响主事件循环
    │  等待视频生成完成        │
    │                         │
    └─────────────────────────┘
              ↓
         返回结果给主线程
              ↓
         响应返回给前端
```

**关键代码：**
```python
# 第 27 行：创建线程池（4 个工作线程）
_executor = ThreadPoolExecutor(max_workers=4)

# 第 471-472 行：在线程池中执行同步函数
loop = asyncio.get_event_loop()
video_urls = await loop.run_in_executor(_executor, _generate_gemini_video)
```

**特点：**
- ⚠️ Gemini SDK 是同步的，会阻塞
- ✅ 使用线程池避免阻塞主事件循环
- ✅ 最多 4 个并发视频生成任务
- ⚠️ 直接返回结果，前端需要等待（可能很久）

---

### 模式 3: Redis 队列 + 后台处理 (Gemini 图片生成)

```python
# 使用场景：Gemini 图片生成
elif provider == 'gemini':
    # 检查队列长度
    queue_length = redis_client.llen('queue:txt2img')
    if queue_length >= 20:
        raise web.HTTPServiceUnavailable(reason='系统繁忙')
    
    # 生成任务 ID
    task_id = str(uuid.uuid4())
    
    # 任务数据
    task_payload = {
        'task_id': task_id,
        'provider': 'gemini',
        'model': model_name,
        'prompt': prompt,
        'api_key': api_key,
        'base_url': base_url,
        'image_b64_list': image_b64_list,
    }
    
    # 推入 Redis 队列
    redis_client.lpush('queue:txt2img', json_lib.dumps(task_payload))
    redis_client.setex(f'task:{task_id}:status', 3600, 'pending')
    
    # 立即返回 task_id
    return web.json_response({'task_id': task_id})
```

**流程图：**
```
前端请求 → aiohttp 异步处理
              ↓
         生成 task_id
              ↓
    将任务推入 Redis 队列
              ↓
    立即返回 task_id 给前端  ← 不等待结果
              ↓
         前端开始轮询
              │
              │
    ┌─────────┴──────────────────────────────────┐
    │                                            │
    │  后台 Worker 进程 (独立运行)                │
    │                                            │
    │  while True:                               │
    │      task = redis_client.rpop('queue:txt2img')  │
    │      if task:                              │
    │          # 调用 Gemini SDK 生成图片        │
    │          result = generate_image(...)      │
    │          # 保存结果到 Redis                │
    │          redis_client.set(f'task:{task_id}:result', result)  │
    │          redis_client.set(f'task:{task_id}:status', 'completed')  │
    │      time.sleep(1)                         │
    │                                            │
    └────────────────────────────────────────────┘
              ↑
              │
    前端轮询: GET /api-proxy/task/{task_id}
              ↓
    返回状态: pending / completed / failed
```

**特点：**
- ✅ 立即返回，不阻塞前端
- ✅ 支持高并发（队列缓冲）
- ✅ 任务持久化（Redis）
- ⚠️ 需要独立的 Worker 进程处理队列
- ⚠️ 前端需要轮询获取结果

---

### 模式 4: 通用异步 API (其他模型)

```python
# 使用场景：其他第三方模型
else:
    payload = {
        'model': model_name,
        'input': [{'params': {'prompt': prompt}}]
    }
    
    # 异步 HTTP 请求
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            data = await resp.json()
    
    task_id = data.get('id')
    # 返回 task_id，前端轮询上游 API
    return web.json_response({'task_id': task_id})
```

**流程图：**
```
前端请求 → aiohttp 异步处理
              ↓
    异步调用上游 API (aiohttp)
              ↓
    上游返回 task_id
              ↓
    返回 task_id 给前端
              ↓
    前端轮询: GET /api-proxy/task/{task_id}
              ↓
    后端查询上游 API 状态
              ↓
    返回状态给前端
```

**特点：**
- ✅ 完全异步，不阻塞
- ✅ 依赖上游 API 的异步机制
- ⚠️ 前端需要轮询

---

## 数据库查询流程

```
前端传递: { model: 1 }  ← 模型表主键 ID
    ↓
routes.py: txt2img()
    ↓
db_queries.get_model_by_id(1)
    ↓
返回: {
    id: 1,
    name: "flux-1.1-pro",      ← 实际模型名称
    type: "image",
    rfid: 5                    ← provider_id
}
    ↓
db_queries.get_provider_by_id(5)
    ↓
返回: {
    id: 5,
    url: "https://api.example.com",
    key: "sk-xxx..."
}
    ↓
使用 model.name 调用上游 API
```

---

## 为什么需要多线程/队列？

### 问题：Gemini SDK 是同步的

```python
# ❌ 如果直接在异步函数中调用同步 SDK
async def txt2video(request):
    client = genai.Client(...)
    operation = client.models.generate_videos(...)  # 同步调用
    
    # 轮询等待（阻塞！）
    for _ in range(30):
        if operation.done:
            break
        time.sleep(10)  # ← 阻塞整个事件循环！
    
    # 问题：在这 5 分钟内，整个服务器无法处理其他请求！
```

### 解决方案 1：线程池

```python
# ✅ 使用线程池
def _generate_gemini_video():  # 同步函数
    # ... 同步调用和 sleep
    time.sleep(10)  # 只阻塞这个线程

# 在线程池中运行
video_urls = await loop.run_in_executor(_executor, _generate_gemini_video)
# 主事件循环继续处理其他请求
```

### 解决方案 2：Redis 队列

```python
# ✅ 推入队列，立即返回
redis_client.lpush('queue:txt2img', task_data)
return {'task_id': task_id}  # 立即返回

# 后台 Worker 慢慢处理
# 主服务器继续接收新请求
```

---

## 总结对比

| 模式 | 使用场景 | 优点 | 缺点 |
|------|---------|------|------|
| OpenAI SDK | DALL-E | 原生异步，简单 | 依赖 OpenAI SDK |
| 线程池 | Gemini 视频 | 不阻塞主线程 | 线程数有限(4)，前端等待久 |
| Redis 队列 | Gemini 图片 | 高并发，立即返回 | 需要 Worker 进程，架构复杂 |
| 通用异步 | 其他模型 | 完全异步 | 依赖上游 API 支持 |

---

## Worker 进程实现

✅ **已有完整的 Worker 实现：`worker.py`**

### Worker 架构

```python
# worker.py - 多线程 Worker 进程

def worker_loop(worker_id: int):
    """单个 worker 线程的主循环"""
    while True:
        # 阻塞式拉取任务（超时 1 秒）
        result = redis_client.brpop('queue:txt2img', timeout=1)
        
        if result:
            queue_name, task_json = result
            task = json.loads(task_json)
            
            if task['provider'] == 'gemini':
                process_gemini_task(task)

def process_gemini_task(task):
    """处理 Gemini 生成任务"""
    # 1. 更新状态为 processing
    redis_client.set(f'task:{task_id}:status', 'processing')
    
    # 2. 调用 Gemini SDK
    client = genai.Client(...)
    response = client.models.generate_content(
        model=task['model'],
        contents=contents
    )
    
    # 3. 保存图片到 D:\AAAA\output
    for part in response.parts:
        if hasattr(part, 'as_image'):
            image = part.as_image()
            image.save(save_path)
    
    # 4. 写入 assets 表
    cursor.execute('INSERT INTO assets ...')
    
    # 5. 更新 Redis 状态为 completed
    redis_client.set(f'task:{task_id}:status', 'completed')
    redis_client.setex(f'task:{task_id}:result', 3600, json.dumps(result))

def main():
    # 启动 4 个 worker 线程并发处理队列
    num_workers = 4
    for i in range(num_workers):
        thread = threading.Thread(target=worker_loop, args=(i+1,))
        thread.start()
```

### 启动 Worker

```bash
# 在 ComfyUI custom_nodes 目录下运行
cd D:\CU\ComfyUI\custom_nodes\comfy_api_proxy
python worker.py
```

### Worker 特点

- ✅ **多线程并发**：4 个线程同时处理队列
- ✅ **阻塞式拉取**：`brpop` 避免空轮询，节省 CPU
- ✅ **自动重试**：异常后继续运行
- ✅ **状态管理**：pending → processing → completed/failed
- ✅ **结果持久化**：保存到文件 + 数据库 + Redis
- ✅ **超时控制**：Redis 结果 1 小时后自动过期

### 完整流程（含 Worker）

```
前端请求
    ↓
routes.py: 推入 Redis 队列
    ↓
立即返回 task_id
    ↓
前端开始轮询 /api-proxy/task/{task_id}
    │
    │  ┌──────────────────────────────────────┐
    │  │  Worker 进程 (独立运行)              │
    │  │                                      │
    │  │  Thread-1  Thread-2  Thread-3  ...  │
    │  │     ↓         ↓         ↓            │
    │  │  brpop    brpop    brpop             │
    │  │     ↓         ↓         ↓            │
    │  │  处理任务  处理任务  处理任务         │
    │  │     ↓         ↓         ↓            │
    │  │  更新状态  更新状态  更新状态         │
    │  │                                      │
    │  └──────────────────────────────────────┘
    │              ↓
    │    Redis: task:{id}:status = 'completed'
    │    Redis: task:{id}:result = {...}
    │              ↓
    └──> 前端轮询获取到结果
```

### 注意事项

⚠️ **Worker 必须单独启动**

Worker 是独立进程，不会随 ComfyUI 自动启动。需要手动运行：

```bash
python worker.py
```

或者配置为系统服务（Windows 服务 / Linux systemd）自动启动。
