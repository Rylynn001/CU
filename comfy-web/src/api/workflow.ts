import { authFetch } from './apiService'

export interface WorkflowMessageRequest {
  message: string
  session_id?: string
}

export interface WorkflowMessageResponse {
  session_id: string
  reply: string
  next_steps?: string[]
  generated_workflow?: any
}

export interface LanguageModel {
  id: number
  name: string
  provider: string
  type: string
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
  return res.json()
}

/**
 * 获取会话历史
 */
export async function getSessionHistory(sessionId: string) {
  const res = await authFetch(`/api/api-proxy/workflow/sessions/${sessionId}`, {
    method: 'GET',
  })
  return res.json()
}
