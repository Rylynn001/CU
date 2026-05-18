// 中间层 API 服务，对接 ComfyUI custom_node: comfy_api_proxy
// 所有请求走 /api-proxy/* (同 ComfyUI 端口，Vite dev 代理已配置 /api → ComfyUI)

const BASE = '/api/api-proxy'

export interface ApiModel {
  id: string
  name: string
  description: string
  type?: 'image' | 'video'
}

export interface ApiGenerateParams {
  model: string
  prompt: string
  width: number
  height: number
  n?: number
  input_asset_ids?: number[]
  user_id?: number
}

export interface ApiGenerateResult {
  images: Array<{ b64?: string; url?: string }>
  taskId?: string
}

// ── Config ────────────────────────────────────────────────────────────────

export async function getApiConfig(): Promise<{ base_url: string; has_key: boolean }> {
  const res = await fetch(`${BASE}/config`)
  if (!res.ok) throw new Error(`config fetch failed: ${res.status}`)
  return res.json()
}

export async function saveApiConfig(payload: { api_key?: string; base_url?: string }): Promise<void> {
  const res = await fetch(`${BASE}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`config save failed: ${res.status}`)
}

// ── Models ────────────────────────────────────────────────────────────────

export async function getApiModels(type?: 'image' | 'video'): Promise<ApiModel[]> {
  const url = type ? `${BASE}/models?type=${type}` : `${BASE}/models`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`models fetch failed: ${res.status}`)
  const data = await res.json()
  return data.models || []
}

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

export async function deleteApiModel(modelId: string): Promise<void> {
  const res = await fetch(`${BASE}/models/${encodeURIComponent(modelId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`delete model failed: ${res.status}`)
}

// ── Input Image Upload ────────────────────────────────────────────────────

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
    return { taskId: data.task_id, images: [] } as any
  } else if (data.images) {
    return data
  } else {
    throw new Error('Invalid response format')
  }
}

export async function pollTaskUntilDone(taskId: string, userId?: number, expectedType: 'image' | 'video' = 'image'): Promise<ApiGenerateResult> {
  return pollTaskStatus(taskId, expectedType, userId)
}

// 把返回的 b64 或 url 转成可直接用于 <img src> 的字符串
export function resolveImageSrc(item: { b64?: string; url?: string }): string {
  if (item.b64) return `data:image/png;base64,${item.b64}`
  if (item.url) return item.url
  return ''
}

// ── Video Generate ─────────────────────────────────────────────────────────

export interface ApiVideoParams {
  model: string
  prompt: string
  user_id?: number
  ratio?: string
  resolution?: string
  duration?: number
}

export interface ApiVideoResult {
  video_url: string
}

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

  // 判断返回类型
  if (data.task_id) {
    // 异步任务，直接返回 task_id，由调用方轮询
    return { task_id: data.task_id }
  } else if (data.video_url) {
    // 直接返回结果
    return data
  } else {
    throw new Error('Invalid response format')
  }
}

// ── Image/Video to Video ───────────────────────────────────────────────────

export interface ApiImg2VideoParams {
  model: string
  prompt: string
  user_id?: number
  ratio?: string
  resolution?: string
  duration?: number
  input_asset_ids?: number[]
}

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

export interface HistoryRecord {
  id: number
  task_id?: string
  prompt: string
  mode?: string
  status?: string
  type?: string
  message?: string
  output_urls: Array<{ url: string; type: string }>
  input_asset_ids: number[]
}

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

export async function fetchHistory(userId: number): Promise<HistoryRecord[]> {
  const res = await fetch(`${BASE}/history?user_id=${userId}`)
  if (!res.ok) throw new Error(`fetch history failed: ${res.status}`)
  const data = await res.json()
  return data.records || []
}

export async function deleteHistory(historyId: number, userId: number): Promise<void> {
  const res = await fetch(`${BASE}/history/${historyId}?user_id=${userId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`delete history failed: ${res.status}`)
}

export async function clearHistory(userId: number): Promise<void> {
  const res = await fetch(`${BASE}/history?user_id=${userId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`clear history failed: ${res.status}`)
}

// ── Task Cancel / Priority ────────────────────────────────────────────────

export async function cancelTask(taskId: string, userId?: number): Promise<void> {
  const url = userId
    ? `${BASE}/task/${taskId}/cancel?user_id=${userId}`
    : `${BASE}/task/${taskId}/cancel`
  await fetch(url, { method: 'POST' })
}

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

// 自定义错误类，用于区分任务失败和网络错误
class TaskFailedError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'TaskFailedError'
  }
}

/**
 * 轮询任务状态，使用指数退避策略
 *
 * 轮询策略：
 * - 前 5 次：每 5 秒查询一次（快速响应）
 * - 5-20 次：每 10 秒查询一次
 * - 20 次后：每 30 秒查询一次
 *
 * 最长轮询时间：约 30 分钟
 */
async function pollTaskStatus(taskId: string, expectedType: 'image' | 'video', userId?: number): Promise<ApiGenerateResult> {
  const maxAttempts = 100 // 最多轮询 100 次（约 30 分钟）

  // 指数退避策略
  const getInterval = (attempt: number): number => {
    if (attempt < 20) return 10000     // 0-20 次：10 秒
    return 30000                       // 20 次后：30 秒
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
        // 任务完成，提取结果
        const results = data.result || []
        const images = results
          .filter(item => item.type === expectedType)
          .map(item => ({ url: item.url }))

        if (images.length === 0) {
          throw new TaskFailedError(`No ${expectedType} generated`)
        }

        return { images }
      } else if (data.status === 'failed') {
        // 任务失败，立即抛出错误，不重试
        const errorMsg = data.error?.error_message || 'Generation failed'
        throw new TaskFailedError(errorMsg)
      }

      // 任务进行中，使用指数退避等待
      const interval = getInterval(i)
      console.log(`[Poll ${i + 1}/${maxAttempts}] Task ${taskId} status: ${data.status}, next check in ${interval}ms`)
      await new Promise(resolve => setTimeout(resolve, interval))

    } catch (error) {
      // 如果是任务失败错误，立即抛出，不重试
      if (error instanceof TaskFailedError) {
        throw error
      }

      // 网络错误或其他异常，等待后重试
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
