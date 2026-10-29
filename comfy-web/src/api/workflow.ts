import { authFetch } from './apiService'

export interface WorkflowMessageRequest {
  message: string
  model_id: number
  session_id?: string
  generation_options?: {
    media_type: 'image' | 'video' | null
    model: number | null
    n?: number | null
    aspect_ratio?: string | null
    quality?: string | null
    ratio?: string | null
    resolution?: string | null
    duration?: number | null
  }
}

export interface WorkflowMessageResponse {
  session_id: string
  reply: string
  intent?: string | null
  parameters?: Record<string, unknown> | null
  workflow_ready: boolean
  tasks: WorkflowTask[]
  generation_request?: { media_type: 'image' | 'video'; prompt: string; models: GenerationModel[] } | null
}

export interface LanguageModel {
  id: number
  name: string
  provider: string
  type: string
}

export interface GenerationModel {
  id: number
  name: string
  provider: string
  description?: string
}

export interface WorkflowSession {
  id: string
  intent: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface ConversationMessage {
  role: 'user' | 'agent'
  message: string
  created_at: string
}

export interface SessionDetail {
  id: string
  intent: string | null
  parameters: any
  status: string
  conversations: ConversationMessage[]
  tasks: WorkflowTask[]
}

export interface WorkflowTask {
  task_id: string
  execution_id: string
  status: 'running' | 'completed' | 'failed' | string
  stage?: string
  error?: string
  model_name?: string
  parameters: { prompt?: string; n?: number; aspect_ratio?: string; quality?: string; ratio?: string; resolution?: string; duration?: number }
  images: Array<{ url: string; asset_id: number }>
}

/**
 * 获取语言模型列表
 */
export async function getLanguageModels(): Promise<LanguageModel[]> {
  const res = await authFetch('/api/api-proxy/models?type=language', {
    method: 'GET',
  })
  const data = await res.json()
  return data.models || []
}

export async function getTaskStatus(taskId: string): Promise<Record<string, any>> {
  const res = await authFetch(`/api/api-proxy/task/${taskId}`, { method: 'GET' })
  if (!res.ok) throw new Error(`任务状态查询失败（${res.status}）`)
  return res.json()
}

/**
 * 流式发送工作流消息，实时读取进度和回复片段。
 */
export async function sendWorkflowMessageStream(
  data: WorkflowMessageRequest,
  onProgress: (message: string) => void,
  onDelta: (text: string) => void,
): Promise<WorkflowMessageResponse> {
  const res = await authFetch('/api/api-proxy/workflow/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : `请求失败（${res.status}）`)
  }
  if (!res.body) throw new Error('浏览器不支持流式响应')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: WorkflowMessageResponse | undefined

  const handleEvent = (block: string) => {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event: ')) event = line.slice(7)
      else if (line.startsWith('data: ')) data.push(line.slice(6))
    }
    if (!data.length) return
    const payload = JSON.parse(data.join('\n'))
    if (event === 'progress') onProgress(payload.message)
    else if (event === 'delta') onDelta(payload.text)
    else if (event === 'done') result = payload as WorkflowMessageResponse
    else if (event === 'error') throw new Error(payload.message || '对话请求失败')
  }

  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() || ''
      for (const block of blocks) handleEvent(block)
      if (done) break
    }
    if (buffer.trim()) handleEvent(buffer)
  } finally {
    reader.releaseLock()
  }

  if (!result) throw new Error('流式响应未正常结束')
  return result
}

/**
 * 获取会话历史
 */
export async function getSessionHistory(sessionId: string): Promise<SessionDetail> {
  const res = await authFetch(`/api/api-proxy/workflow/sessions/${sessionId}`, {
    method: 'GET',
  })
  return res.json()
}

/**
 * 获取用户的所有会话列表
 */
export async function getUserSessions(): Promise<WorkflowSession[]> {
  const res = await authFetch('/api/api-proxy/workflow/sessions', {
    method: 'GET',
  })
  return res.json()
}
