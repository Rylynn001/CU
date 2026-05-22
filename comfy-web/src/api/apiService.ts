// 中间层 API 服务，对接 ComfyUI custom_node: comfy_api_proxy
// 所有请求走 /api/api-proxy/* (同 ComfyUI 端口，Vite dev 代理已配置 /api → ComfyUI)

const BASE = '/api/api-proxy'

// ── 类型定义 ──────────────────────────────────────────────────────────────

// API 模型信息
export interface ApiModel {
  id: string
  name: string
  description: string
  type?: 'image' | 'video'
}

// 图片生成请求参数
export interface ApiGenerateParams {
  model: string
  prompt: string
  width: number
  height: number
  n?: number               // 生成数量，默认 1
  input_asset_ids?: number[] // 图生图时传入的参考图资产 id 列表
  user_id?: number
}

// 图片生成结果（同步返回图片 或 异步返回 taskId）
export interface ApiGenerateResult {
  images: Array<{ b64?: string; url?: string }>
  taskId?: string
}

// ── Config ────────────────────────────────────────────────────────────────

// 获取当前 API 配置（base_url 和是否已设置 key）
export async function getApiConfig(): Promise<{ base_url: string; has_key: boolean }> {
  const res = await fetch(`${BASE}/config`)
  if (!res.ok) throw new Error(`config fetch failed: ${res.status}`)
  return res.json()
}

// 保存 API 配置（api_key 和/或 base_url）
export async function saveApiConfig(payload: { api_key?: string; base_url?: string }): Promise<void> {
  const res = await fetch(`${BASE}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`config save failed: ${res.status}`)
}

// ── Models ────────────────────────────────────────────────────────────────

// 获取可用模型列表，可按 type 过滤（image / video）
export async function getApiModels(type?: 'image' | 'video'): Promise<ApiModel[]> {
  const url = type ? `${BASE}/models?type=${type}` : `${BASE}/models`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`models fetch failed: ${res.status}`)
  const data = await res.json()
  return data.models || []
}

// 新增模型配置
export async function addApiModel(model: ApiModel): Promise<void> {
  const res = await fetch(`${BASE}/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(model),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `add model failed: ${res.status}`)
  }
}

// 删除模型配置
export async function deleteApiModel(modelId: string): Promise<void> {
  const res = await fetch(`${BASE}/models/${encodeURIComponent(modelId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`delete model failed: ${res.status}`)
}

// ── Input Image Upload ────────────────────────────────────────────────────

// 上传参考图到后端资产库，返回资产 id 和存储路径
export async function uploadInputImage(file: File, userId: number): Promise<{ id: number; location: string }> {
  const form = new FormData()
  form.append('file', file)
  form.append('user_id', String(userId))
  const res = await fetch(`${BASE}/upload/image`, { method: 'POST', body: form })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `upload failed: ${res.status}`)
  }
  return res.json()
}

// ── Generate ──────────────────────────────────────────────────────────────

// 提交图片生成任务
// 后端可能同步返回图片（images），也可能返回 task_id 表示异步任务
export async function apiGenerate(params: ApiGenerateParams): Promise<ApiGenerateResult> {
  const res = await fetch(`${BASE}/txt2img`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `generate failed: ${res.status}`)
  }
  const data = await res.json()

  if (data.task_id) {
    // 异步任务：返回 taskId，由调用方轮询
    return { taskId: data.task_id, images: [] } as any
  } else if (data.images) {
    // 同步任务：直接返回图片
    return data
  } else {
    throw new Error('Invalid response format')
  }
}

// 轮询任务直到完成（对外暴露的简化入口，内部调用 pollTaskStatus，定义在文件末尾）
export async function pollTaskUntilDone(taskId: string, userId?: number, expectedType: 'image' | 'video' = 'image'): Promise<ApiGenerateResult> {
  return pollTaskStatus(taskId, expectedType, userId)
}

// 将后端返回的图片对象转为 <img src> 可用的字符串
// 优先使用 url，其次将 base64 拼成 data URI
export function resolveImageSrc(item: { b64?: string; url?: string }): string {
  if (item.b64) return `data:image/png;base64,${item.b64}`
  if (item.url) return item.url
  return ''
}

// ── Video Generate ─────────────────────────────────────────────────────────

// 文生视频请求参数
export interface ApiVideoParams {
  model: string
  prompt: string
  user_id?: number
  ratio?: string       // 画面比例，如 "16:9"
  resolution?: string  // 分辨率，如 "1080p"
  duration?: number    // 时长（秒）
}

export interface ApiVideoResult {
  video_url: string
}

// 提交文生视频任务
// 后端可能同步返回 video_url，也可能返回 task_id 表示异步任务
export async function apiVideoGenerate(params: ApiVideoParams): Promise<ApiVideoResult | { task_id: string }> {
  const res = await fetch(`${BASE}/txt2video`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `video generate failed: ${res.status}`)
  }
  const data = await res.json()

  if (data.task_id) {
    // 异步任务，直接返回 task_id，由调用方轮询
    return { task_id: data.task_id }
  } else if (data.video_url) {
    // 同步返回结果
    return data
  } else {
    throw new Error('Invalid response format')
  }
}

// ── Image/Video to Video ───────────────────────────────────────────────────

// 图生视频请求参数（比文生视频多了 input_asset_ids）
export interface ApiImg2VideoParams {
  model: string
  prompt: string
  user_id?: number
  ratio?: string
  resolution?: string
  duration?: number
  input_asset_ids?: number[] // 参考图/视频的资产 id 列表
}

// 提交图生视频任务，始终返回 task_id（异步）
export async function apiImg2VideoGenerate(params: ApiImg2VideoParams): Promise<{ task_id: string }> {
  const form = new FormData()
  form.append('model', params.model)
  form.append('prompt', params.prompt)
  if (params.user_id) form.append('user_id', String(params.user_id))
  if (params.ratio) form.append('ratio', params.ratio)
  if (params.resolution) form.append('resolution', params.resolution)
  if (params.duration) form.append('duration', String(params.duration))
  if (params.input_asset_ids && params.input_asset_ids.length > 0) {
    form.append('input_asset_ids', params.input_asset_ids.join(','))
  }

  const res = await fetch(`${BASE}/img2video`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `img2video generate failed: ${res.status}`)
  }
  const data = await res.json()
  return { task_id: data.task_id }
}

// ── History ───────────────────────────────────────────────────────────────

// 历史记录条目（从后端返回）
export interface HistoryRecord {
  id: number
  task_id?: string
  prompt: string
  mode?: string
  status?: string
  type?: string
  message?: string
  model_name?: string
  output_urls: Array<{ url: string; type: string }>
  input_asset_ids: number[]
  input_asset_urls: Array<{ url: string; type: string }>
}

// 保存一条历史记录到后端数据库
export async function saveHistory(params: {
  user_id: number
  prompt: string
  output_urls: string[]
  input_asset_ids?: number[]
  task_id?: string
  mode?: string
  status?: string
  type?: string
  message?: string
  model_id?: number
}): Promise<{ id: number }> {
  const res = await fetch(`${BASE}/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`save history failed: ${res.status}`)
  return res.json()
}

// 拉取指定用户的历史记录，可按 type 过滤（img / video）
export async function fetchHistory(userId: number, type?: 'img' | 'video'): Promise<HistoryRecord[]> {
  const url = type ? `${BASE}/history?user_id=${userId}&type=${type}` : `${BASE}/history?user_id=${userId}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`fetch history failed: ${res.status}`)
  const data = await res.json()
  return data.records || []
}

// 删除单条历史记录
export async function deleteHistory(historyId: number, userId: number): Promise<void> {
  const res = await fetch(`${BASE}/history/${historyId}?user_id=${userId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`delete history failed: ${res.status}`)
}

// 清空指定用户的所有历史记录
export async function clearHistory(userId: number): Promise<void> {
  const res = await fetch(`${BASE}/history?user_id=${userId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`clear history failed: ${res.status}`)
}

// ── Task Cancel / Priority ────────────────────────────────────────────────

// 取消正在排队或执行中的任务
export async function cancelTask(taskId: string, userId?: number): Promise<void> {
  const url = userId
    ? `${BASE}/task/${taskId}/cancel?user_id=${userId}`
    : `${BASE}/task/${taskId}/cancel`
  await fetch(url, { method: 'POST' })
}

// 将任务插队到队列最前面
export async function prioritizeTask(taskId: string, userId?: number): Promise<void> {
  const url = userId
    ? `${BASE}/task/${taskId}/priority?user_id=${userId}`
    : `${BASE}/task/${taskId}/priority`
  const res = await fetch(url, { method: 'POST' })
  if (!res.ok) throw new Error('插队失败')
}

// ── Task Polling ──────────────────────────────────────────────────────────

interface TaskStatusResponse {
  status: 'in_progress' | 'completed' | 'failed' | 'pending' | 'processing'
  error?: { code: number; error_message: string }
  result?: Array<{ url: string; type: string }>
}

// 区分"任务本身失败"和"网络/超时错误"，前者不重试
class TaskFailedError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'TaskFailedError'
  }
}

/**
 * 轮询任务状态，使用阶梯式间隔策略：
 * - 前 20 次：每 10 秒查询一次
 * - 20 次后：每 30 秒查询一次
 * 最长轮询约 30 分钟（100 次）
 */
async function pollTaskStatus(taskId: string, expectedType: 'image' | 'video', userId?: number): Promise<ApiGenerateResult> {
  const maxAttempts = 100

  const getInterval = (attempt: number): number => {
    if (attempt < 20) return 10000  // 前 20 次 10 秒
    return 30000                    // 之后 30 秒
  }

  for (let i = 0; i < maxAttempts; i++) {
    const url = userId ? `${BASE}/task/${taskId}?user_id=${userId}` : `${BASE}/task/${taskId}`

    try {
      const res = await fetch(url)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `task query failed: ${res.status}`)
      }

      const data: TaskStatusResponse = await res.json()

      if (data.status === 'completed') {
        // 任务完成，提取对应类型的结果
        const results = data.result || []
        const images = results
          .filter(item => item.type === expectedType)
          .map(item => ({ url: item.url }))

        if (images.length === 0) {
          throw new TaskFailedError(`No ${expectedType} generated`)
        }

        return { images }
      } else if (data.status === 'failed') {
        // 任务失败，立即抛出，不重试
        const errorMsg = data.error?.error_message || 'Generation failed'
        throw new TaskFailedError(errorMsg)
      }

      // 任务进行中，等待后继续轮询
      const interval = getInterval(i)
      console.log(`[Poll ${i + 1}/${maxAttempts}] Task ${taskId} status: ${data.status}, next check in ${interval}ms`)
      await new Promise(resolve => setTimeout(resolve, interval))

    } catch (error) {
      // TaskFailedError 直接抛出，不重试
      if (error instanceof TaskFailedError) {
        throw error
      }

      // 网络错误等待后重试
      if (i < maxAttempts - 1) {
        const interval = getInterval(i)
        console.warn(`[Poll ${i + 1}] Error querying task ${taskId}, retrying in ${interval}ms:`, error)
        await new Promise(resolve => setTimeout(resolve, interval))
      } else {
        throw error
      }
    }
  }

  throw new Error('Task timeout after 30 minutes')
}
