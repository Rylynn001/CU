import { authFetch } from './apiService'

export interface WorkflowMessageRequest {
  message: string
  session_id?: string
}

export interface WorkflowMessageResponse {
  session_id: string
  reply: string
  intent?: string | null
  parameters?: Record<string, unknown> | null
  workflow_ready: boolean
}

export interface LanguageModel {
  id: number
  name: string
  provider: string
  type: string
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

/**
 * 发送工作流消息
 */
export async function sendWorkflowMessage(data: WorkflowMessageRequest): Promise<WorkflowMessageResponse> {
  const res = await authFetch('/api/api-proxy/workflow/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => null)
    const detail = typeof error?.detail === 'string' ? error.detail : `请求失败（${res.status}）`
    throw new Error(detail)
  }
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
