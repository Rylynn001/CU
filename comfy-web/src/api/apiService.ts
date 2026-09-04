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
  model: number
  prompt: string
  aspect_ratio: string     // 比例，如 "1:1"、"16:9"，后端按模型映射
  quality: string          // 清晰度，如 "low"/"medium"/"high"，后端按模型映射
  n?: number               // 生成数量，默认 1
  input_asset_ids?: number[] // 图生图时传入的参考图资产 id 列表
  user_id?: number
}

// 图片生成结果（同步返回图片 或 异步返回 taskId）
export interface ApiGenerateResult {
  images: Array<{ b64?: string; url?: string; asset_id?: number }>
  taskId?: string
  historyId?: number
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
  const res = await fetch(`${BASE}/upload/file`, { method: 'POST', body: form })
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
    return { taskId: data.task_id, historyId: data.history_id, images: [] }
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
  model: string | number
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
export async function apiVideoGenerate(params: ApiVideoParams): Promise<ApiVideoResult | { task_id: string; history_id?: number }> {
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
    return { task_id: data.task_id, history_id: data.history_id }
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
  model: string | number
  prompt: string
  user_id?: number
  ratio?: string
  resolution?: string
  duration?: number
  input_asset_ids?: number[]
}

// 提交图生视频任务，始终返回 task_id（异步）
export async function apiImg2VideoGenerate(params: ApiImg2VideoParams): Promise<{ task_id: string; history_id?: number }> {
  const res = await fetch(`${BASE}/img2video`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `img2video generate failed: ${res.status}`)
  }
  const data = await res.json()
  return { task_id: data.task_id, history_id: data.history_id }
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
  model_id?: number
  output_urls: Array<{ url: string; type: string; id?: number }>
  input_asset_ids: number[]
  input_asset_urls: Array<{ url: string; type: string }>
  payload?: any  // 完整的生成参数，包含所有配置
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

// 根据资产 id 反查其所属的历史记录（用于资产库右键"定位历史记录"）
export async function fetchHistoryByAsset(assetId: number, userId: number): Promise<HistoryRecord> {
  const res = await fetch(`${BASE}/history/by-asset/${assetId}?user_id=${userId}`)
  if (!res.ok) throw new Error(`fetch history by asset failed: ${res.status}`)
  const data = await res.json()
  return data.record
}

// 拉取指定用户的历史记录，可按 type 过滤（img / video）
export async function fetchHistory(
  userId: number,
  type?: 'img' | 'video',
  page = 1,
  pageSize: 30 | 50 | 100 = 30,
): Promise<{ records: HistoryRecord[]; total: number }> {
  let url = `${BASE}/history?user_id=${userId}&page=${page}&page_size=${pageSize}`
  if (type) url += `&type=${type}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`fetch history failed: ${res.status}`)
  const data = await res.json()
  return { records: data.records || [], total: data.total ?? 0 }
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

// 重试失败的历史记录：后端读取 payload 重新入队，旧记录软删除
export async function retryHistory(historyId: number): Promise<{ task_id: string; history_id: number }> {
  const res = await fetch(`${BASE}/history/${historyId}/retry`, { method: 'POST' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `retry failed: ${res.status}`)
  }
  return res.json()
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
  historyId?: number
  constructor(message: string, historyId?: number) {
    super(message)
    this.name = 'TaskFailedError'
    this.historyId = historyId
  }
}

/**
 * 轮询任务状态，使用阶梯式间隔策略：
 * - 前 20 次：每 10 秒查询一次
 * - 20 次后：每 60 秒查询一次
 * 最长轮询约 100 分钟（120 次）
 */
async function pollTaskStatus(taskId: string, expectedType: 'image' | 'video', userId?: number): Promise<ApiGenerateResult> {
  const maxAttempts = 120

  const getInterval = (attempt: number): number => {
    if (attempt < 20) return 2000   // 前 20 次 2 秒
    return 60000                    // 之后 60 秒
  }

  for (let i = 0; i < maxAttempts; i++) {
    const url = userId ? `${BASE}/task/${taskId}?user_id=${userId}` : `${BASE}/task/${taskId}`

    try {
      const res = await fetch(url)
      if (!res.ok) {
        const text = await res.text()
        // 404 表示任务不存在或已过期，属于终态，不重试
        if (res.status === 404) throw new TaskFailedError(text || 'Task not found or expired')
        throw new Error(text || `task query failed: ${res.status}`)
      }

      const data: TaskStatusResponse = await res.json()

      if (data.status === 'completed') {
        // 任务完成，提取对应类型的结果
        const results = data.result || []
        const images = results
          .filter(item => item.type === expectedType)
          .map(item => ({ url: item.url, asset_id: (item as any).asset_id }))

        if (images.length === 0) {
          throw new TaskFailedError(`No ${expectedType} generated`)
        }

        return { images, inputAssetUrls: (data as any).input_asset_urls, historyId: (data as any).history_id }
      } else if (data.status === 'failed') {
        // 任务失败，立即抛出，不重试
        const errorMsg = data.error?.error_message || 'Generation failed'
        throw new TaskFailedError(errorMsg, (data as any).history_id)
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

  throw new Error('Task timeout after 100 minutes')
}

// ── Assets Favorite ───────────────────────────────────────────────────────

export async function favoriteAsset(assetId: number, userId: number, tag: 0 | 1 | 2 | 3 | 4): Promise<void> {
  const res = await fetch(`${BASE}/user/assets/${assetId}/favorite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, tag }),
  })
  if (!res.ok) throw new Error(`favorite failed: ${res.status}`)
}

// ── 团队协作：成员与审核 ────────────────────────────────────────────────────

export type MemberRole = 'owner' | 'admin' | 'member'

export interface ProjectMember {
  user_id: number
  role: MemberRole
  user_name: string | null
  real_name: string | null
}

// 待审核素材
export interface PendingAsset {
  id: number   // category_assets 行 id
  category_id: number
  assets_id: number
  submitted_by: number
  submitted_by_name: string | null
  created_at: string | null
  category_name: string
  project_id: number   // 所属项目 ID
  project_name: string   // 所属项目名称
  location: string | null
  asset_type: string | null
  reject_count: number   // 该素材在此分类历史上被驳回次数
}

// 审核时间线条目
export interface ReviewEvent {
  action: 'submit' | 'approve' | 'reject'
  comment: string | null
  reviewer_id: number | null
  reviewer_name: string | null
  created_at: string | null
  assets_id: number | null
  location: string | null
  asset_type: string | null
}

// 我的提交条目
export interface MySubmission {
  id: number   // category_assets 行 id，重新提交时用于续接该记录
  category_id: number
  assets_id: number
  review_status: 'pending' | 'approved' | 'rejected'
  created_at: string | null
  category_name: string
  project_id: number
  project_name: string
  location: string | null
  asset_type: string | null
  reject_count: number
}

// 提交素材到分类（member 提交需审核，owner/admin 直接通过）。
// resubmitId：续接一条被驳回的提交记录（MySubmission.id），不传则视为全新提交。
export async function addAssetToCategory(
  categoryId: number, assetId: number, userId: number, resubmitId?: number
): Promise<{ review_status: 'approved' | 'pending' }> {
  const res = await fetch(`${BASE}/categories/${categoryId}/assets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ asset_id: assetId, user_id: userId, resubmit_id: resubmitId }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `add asset failed: ${res.status}`)
  }
  return res.json()
}

// 获取项目成员列表（需当前用户是项目成员）
export async function listMembers(projectId: number, userId: number): Promise<ProjectMember[]> {
  const res = await fetch(`${BASE}/projects/${projectId}/members?user_id=${userId}`)
  if (!res.ok) throw new Error(`list members failed: ${res.status}`)
  const data = await res.json()
  return data.members || []
}

// 候选用户（尚未加入项目的用户）
export interface CandidateUser {
  id: number
  user_name: string
  real_name: string
}

// 获取可添加的候选用户列表（owner/admin 可操作）
export async function listCandidateUsers(
  projectId: number,
  userId: number,
  keyword: string = '',
  page: number = 1,
  pageSize: number = 50
): Promise<{ users: CandidateUser[]; total: number; page: number; page_size: number }> {
  const params = new URLSearchParams({
    user_id: String(userId),
    page: String(page),
    page_size: String(pageSize),
  })
  if (keyword.trim()) {
    params.append('keyword', keyword.trim())
  }
  const res = await fetch(`${BASE}/projects/${projectId}/candidate-users?${params}`)
  if (!res.ok) throw new Error(`list candidate users failed: ${res.status}`)
  return res.json()
}

// 邀请成员（owner/admin 可操作），按用户名添加
export async function addMember(projectId: number, userId: number, username: string, role: MemberRole = 'member'): Promise<void> {
  const res = await fetch(`${BASE}/projects/${projectId}/members`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, username, role }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `add member failed: ${res.status}`)
  }
}

// 设置成员角色（owner/admin 可操作）
export async function setMemberRole(projectId: number, userId: number, targetUserId: number, role: MemberRole): Promise<void> {
  const res = await fetch(`${BASE}/projects/${projectId}/members/${targetUserId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, role }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `set role failed: ${res.status}`)
  }
}

// 移除成员（owner/admin 可操作）
export async function removeMember(projectId: number, userId: number, targetUserId: number): Promise<void> {
  const res = await fetch(`${BASE}/projects/${projectId}/members/${targetUserId}?user_id=${userId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `remove member failed: ${res.status}`)
  }
}

// 获取用户有权限审核的所有待审核素材（跨所有项目）
export async function listPendingAssets(
  userId: number, page = 1, pageSize = 50
): Promise<{ assets: PendingAsset[]; total: number }> {
  const res = await fetch(`${BASE}/pending-assets?user_id=${userId}&page=${page}&page_size=${pageSize}`)
  if (!res.ok) throw new Error(`list pending failed: ${res.status}`)
  const data = await res.json()
  return { assets: data.assets || [], total: data.total ?? 0 }
}

// 审核素材（通过 / 拒绝），可附评语
export async function reviewAsset(categoryId: number, assetId: number, userId: number, approve: boolean, comment?: string): Promise<void> {
  const res = await fetch(`${BASE}/categories/${categoryId}/assets/${assetId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, approve, comment }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `review failed: ${res.status}`)
  }
}

// 查某素材在某分类的审核时间线（owner/admin 或提交人可查）
export async function fetchReviewTimeline(categoryId: number, assetId: number, userId: number): Promise<ReviewEvent[]> {
  const res = await fetch(`${BASE}/categories/${categoryId}/assets/${assetId}/reviews?user_id=${userId}`)
  if (!res.ok) throw new Error(`fetch timeline failed: ${res.status}`)
  return res.json()
}

// 查当前用户在所有项目下的提交（含被驳回的）
export async function listMySubmissions(
  userId: number, page = 1, pageSize = 50
): Promise<{ submissions: MySubmission[]; total: number; rejectedTotal: number }> {
  const res = await fetch(`${BASE}/my-submissions?user_id=${userId}&page=${page}&page_size=${pageSize}`)
  if (!res.ok) throw new Error(`list my submissions failed: ${res.status}`)
  const data = await res.json()
  return {
    submissions: data.submissions || [],
    total: data.total ?? 0,
    rejectedTotal: data.rejected_total ?? 0,
  }
}
