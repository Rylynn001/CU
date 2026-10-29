# `/chat/stream` Agent 实现说明

本文按当前代码说明 `/api-proxy/workflow/chat/stream` 的实现。这里的 Agent 是一个 Python 对象加上模型工具调用循环，不是独立运行、会自行扫描整个后端的程序。

## 先看整体流程

```mermaid
sequenceDiagram
    participant UI as 聊天页面
    participant API as workflow.chat_stream
    participant Agent as ConversationAgent
    participant LLM as 对话模型
    participant Box as WorkflowTools 工具箱
    participant DB as MySQL
    participant Redis as Redis 队列

    UI->>API: POST 消息 / model_id / session_id
    API->>DB: 验证会话归属并加载历史
    API->>Agent: 消息、历史、工具发现器、执行器
    Agent->>LLM: 对话 + discover_tools 描述
    LLM-->>Agent: 普通文字，或请求 discover_tools
    Agent->>Box: 用模型给出的查询词搜索工具目录
    Box-->>Agent: 最多三个匹配工具
    Agent->>LLM: 对话 + 发现结果对应的工具定义
    LLM-->>Agent: 请求调用某个已发现工具
    Agent->>Box: 工具名 + 参数
    Box->>DB: 查询模型、图片、历史或创建执行记录
    Box->>Redis: 生成任务入队
    Box-->>Agent: 工具执行结果
    Agent->>LLM: 把工具结果放回对话，继续生成回复
    LLM-->>Agent: 回复文字分片
    Agent-->>API: on_delta / on_progress 回调
    API-->>UI: SSE delta / progress / done
```

每轮最多请求模型八次，避免模型反复发现或调用工具而无限循环。模型的普通回复会通过 SSE 分片送到页面；完整回复也会保存到会话记录。

## 主要文件和导入

### `api/workflow.py`

这是 HTTP 入口和协调层。

- `asyncio`：创建并等待聊天处理任务，同时从事件队列读取进度和文字。
- `json`：把 SSE 事件编码为 JSON 数据。
- `uuid`：为每次 HTTP 聊天请求生成 `request_id`，用于关联日志。
- `logging`：记录请求开始、完成和异常。
- FastAPI 的 `APIRouter`、`Depends`、`HTTPException`、`StreamingResponse`：注册路由、注入登录用户、返回错误和 SSE 响应。
- Pydantic 的 `BaseModel`、`Field`：定义请求和响应数据结构。
- `get_current_user`：从 Bearer token 解析当前用户身份。
- `ConversationAgent`：负责请求对话模型和处理模型返回的工具调用。
- `WorkflowRepository`：读写聊天会话、聊天消息和工具任务执行记录。
- `get_language_model_info`、`get_provider_config_by_rfid`：从数据库找到对话模型，并取得对应的 API 地址和密钥。
- `WorkflowTools`、`session_tasks`：创建本次请求使用的工具箱，并读取会话任务状态。

`chat_stream()` 负责把 HTTP 连接变成 SSE。`_process_chat()` 负责加载上下文、创建工具箱、调用 Agent，并保存用户消息和最终回复。

### `agents/conversation_agent.py`

这是对话模型调用循环。

- `openai.AsyncOpenAI`：通过 OpenAI 兼容的 Chat Completions 接口调用配置的模型。它只负责网络 API，不负责执行后端工具。
- `json`：序列化消息、工具参数和日志内容。
- `logging`：记录模型调用、模型回复、工具调用和工具返回。
- `time`：统计每次模型请求耗时。
- `typing` 中的 `Callable`、`Awaitable`、`Optional` 等：说明传入回调和可选参数的类型。
- `ConversationState`：对话状态的类型定义，来自项目自己的 `graph.states`。

这个请求路径没有运行 LangGraph 图；`ConversationState` 在这里主要用于标注状态结构。工具调用使用 OpenAI 兼容接口的 `tools` / `tool_calls` JSON Schema，没有使用 MCP、LangChain 工具执行器或 Python 反射自动发现函数。

### `services/workflow_tools.py`

这是工具目录、匹配器和后端处理函数所在的位置。当前注册了图片、视频生成、用户图片查询和生成历史查询。

- `pydantic.BaseModel`、`ConfigDict`、`Field`：校验模型生成的文生图参数；例如限制张数、比例和质量。
- `api.generation` 中的请求模型和函数：复用已有的文生图、文生视频后端接口。
- `provider_repo`：读取数据库中的模型列表。
- `asset_repo`：按当前用户查询图片资产。
- `history_repo`：按当前用户查询生成历史。
- `WorkflowRepository`：将 Agent 提交的任务与聊天会话关联起来，并持久化任务状态。
- `pathlib.Path`、`PureWindowsPath`：只取资产文件名并构造输出 URL，不把本机完整路径返回给模型。
- `logging`：记录图片模型查询和任务提交信息。

工具的定义包含模型可读的名称、说明、参数 Schema，以及用于发现的关键词。Python 处理函数单独保存在 `handlers` 映射中。模型只会收到 JSON Schema，不会收到这些 Python 函数或数据库连接。

## 模型如何判断要不要调用工具

当前没有一段 Python 代码先把用户消息硬分成“生图”“查图片”“查历史”等意图。实际判断分两步：

1. 第一次模型请求只带系统提示、对话历史和 `discover_tools(query)` 定义。模型阅读用户消息后，可以直接回答，也可以请求调用 `discover_tools`，并用自然语言写出它认为需要的能力。
2. 后端的 `discover()` 用该查询词匹配工具目录中的关键词别名，按命中数量排序，最多返回三个工具。Agent 把这些工具的 Schema 加入本轮临时工具集，再发起下一次模型请求。
3. 模型看到实际工具参数后，决定是否调用某个工具，并生成参数。后端检查工具是否已发现、是否注册了执行函数，再由具体处理器校验参数和权限。

因此，“理解用户语义、决定是否找工具”由对话模型完成；“从目录中召回工具”目前由关键词别名匹配完成。当前没有 embedding 或向量检索。目录新增工具时，需要同时补充说明、参数 Schema、关键词别名和处理函数。别名不完整时，即使模型理解了用户意图，后端也可能召回不到工具。

模型列出某个工具不代表工具已经执行。只有模型返回 `tool_calls`，Agent 才会调用后端执行函数。执行结果会作为 `role=tool` 消息交还模型，由模型根据真实结果继续回答。

## 数据从哪里来

- 用户消息、前端选择的语言模型 `model_id` 和可选的 `session_id` 来自前端请求体。后端按 `api_models.id` 精确读取该语言模型。
- 当前用户来自 `get_current_user()`：它验证 JWT 并返回 `user_id`。已有会话会检查数据库中的所有者是否与当前用户一致。
- 历史对话来自 `workflow_conversations` 表，并与系统提示一起发给模型。
- 图片模型和视频模型来自 `api_models` 表；模型列表工具只返回模型编号、名称、描述和提供商，不返回 API 密钥。
- 图片资产来自 `assets` 表，并用当前 `user_id` 查询。
- 生成历史来自 `history` 及其资产关联表，并以当前 `user_id` 过滤。
- 生成参数由模型提供，但不会直接信任：文生图参数使用 Pydantic 校验，选中的模型还必须在本次已查询的可用模型列表中。
- 文生图/文生视频真正提交时，已有的 `api.generation` 接口读取模型与 provider 配置，保存 `history` 记录，并将工作任务放到 Redis 队列。worker 随后实际调用图片或视频生成服务。
- `workflow_executions` 保存聊天会话里的任务编号、历史编号、参数和状态；后续由 `session_tasks()` 查询生成历史并更新完成状态。

## 生命周期：什么会结束，什么会保留

- `get_conversation_agent()` 创建的 `ConversationAgent` 是模块级单例。它和其中的 `AsyncOpenAI` 客户端会随 FastAPI 服务进程保留，不会在每次聊天结束时销毁。
- `WorkflowTools` 在 `_process_chat()` 每次调用时创建一次。它保存本次用户、会话创建函数、已查询的图片/视频模型和工具处理器；请求结束后没有其他模块持有它时，Python 可以回收它。代码没有显式调用 `del` 或专门的 `close()`。
- `available_tools`、本轮 `messages`、模型输出分片和工具调用参数都是 `ConversationAgent.process()` 的局部数据。本轮处理结束后，它们离开作用域，不会自动成为下一轮的工具定义。新一条用户消息会重新从 `discover_tools` 开始。
- 模型服务收到的是对话内容和 JSON Schema。服务端不会向模型发送 Python 函数、数据库句柄或 `WorkflowTools` 对象。
- 每个模型流在 `finally` 中调用 `await stream.close()`。如果浏览器中断连接，SSE 层会取消并等待聊天任务结束。
- 已保存的会话消息、`workflow_executions`、生成历史和 Redis 队列任务不会随 Agent 对象回收而删除；这些是业务数据，按各自的数据库/队列生命周期保留。Agent 对象结束不等于生成任务被取消。

## 两个例子

### 例一：生成图片

用户说：“帮我生成一张海边日落的图片。”

1. `ConversationAgent` 首轮只向模型提供 `discover_tools`。模型可能用“查找文生图能力”作为发现查询。
2. `discover()` 命中 `txt2img`。模型只在下一轮看到文生图的参数 Schema，而不会收到整个后端所有工具。
3. `txt2img` 处理器要求先查询图片模型。因此模型还需要发现并调用 `list_image_models`；模型列表来自数据库。
4. 模型选定真实模型后调用 `txt2img`。服务端校验参数与模型，创建执行记录，调用现有文生图 API，API 保存历史并把任务放入 Redis。
5. 工具结果中的 `task_id`、`history_id` 返回给模型。模型生成最终文字；页面收到 SSE `delta`，接口最后返回包含任务信息的 `done` 事件。

如果用户没有选模型，模型可以先展示查询到的可选模型并追问；不能自行编造模型编号。

### 例二：查看最近的图片

用户说：“帮我找一下最近上传的图片。”

1. 模型用类似“查询当前用户的图片资产”的语句调用 `discover_tools`。
2. 后端召回 `list_my_images`，再把它的分页参数 Schema 提供给模型。
3. 模型调用 `list_my_images`。处理器从 `asset_repo.get_user_assets()` 查询当前 `user_id` 的图片，返回最近一页的资产 ID、文件名和 URL。
4. 模型根据工具结果回答。这个查询只列出资产，不会调用图片生成接口，也不会读取其他用户的资产。

## 如何从日志追踪一次调用

`request_id` 会贯穿 `_process_chat()` 和 Agent 日志。一次请求通常可按下面的字段顺序阅读：

1. `工作流对话开始`：请求用户和会话。
2. `对话模型开始`：模型名、轮次和本轮 `provided_tools`。首轮通常只有 `discover_tools`。
3. `对话模型完成`：本轮完整文字、工具调用数量和耗时。
4. `对话模型请求调用工具`：模型选择的工具和参数。发现工具时，参数里有模型生成的发现查询。
5. `对话工具返回`：发现结果、数据库查询结果或任务编号。
6. 下一轮 `对话模型开始`：此时 `provided_tools` 包含刚发现的工具。
7. `工作流对话完成`：整次对话耗时和最终会话状态。

普通文字在 UI 中是增量显示，但日志按模型每轮完整记录，避免每个 token 各写一条日志。

## 当前能力边界

- 已注册：查询图片模型、文生图、查询视频模型、文生视频、查询当前用户图片、查询当前用户生成历史。
- 未注册：日志查询。当前没有按用户隔离的日志查询服务，不能把整个服务进程的日志直接交给模型查询。
- 未注册：图生视频。现有参考素材读取逻辑尚未证明会校验资产归属，因此当前工具箱没有开放这项能力。
- 发现采用关键词别名匹配，不是任意自然语言的完美语义搜索。发现查询和别名词条不匹配时，工具不会被加载。
