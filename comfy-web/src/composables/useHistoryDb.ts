import { saveHistory, fetchHistory, deleteHistory, clearHistory, type HistoryRecord } from '../api/apiService'

export type { HistoryRecord }

/**
 * 封装历史记录的后端数据库操作。
 * 只负责与后端通信，不持有状态。
 * 视图层负责将 DB 记录合并到本地 records 中。
 */
export function useHistoryDb() {
  // 拉取指定用户的历史记录，失败时返回空数组（不阻断页面）
  async function load(
    userId: number,
    type?: 'img' | 'video',
    page = 1,
    pageSize: 30 | 50 | 100 = 30,
  ): Promise<{ records: HistoryRecord[]; total: number }> {
    try {
      return await fetchHistory(userId, type, page, pageSize)
    } catch (e) {
      console.warn('[useHistoryDb] load failed:', e)
      return { records: [], total: 0 }
    }
  }

  // 保存一条历史记录到后端，返回新记录的 id；失败时返回 null
  async function persist(params: {
    userId: number
    prompt: string
    outputUrls: string[]
    inputAssetIds?: number[]
    taskId?: string
    mode?: string
    status?: string
    type?: string
    message?: string
    modelId?: number
  }): Promise<number | null> {
    try {
      const res = await saveHistory({
        user_id: params.userId,
        prompt: params.prompt,
        output_urls: params.outputUrls,
        input_asset_ids: params.inputAssetIds,
        task_id: params.taskId,
        mode: params.mode,
        status: params.status,
        type: params.type,
        message: params.message,
        model_id: params.modelId,
      })
      return res.id
    } catch (e) {
      console.warn('[useHistoryDb] persist failed:', e)
      return null
    }
  }

  // 删除单条历史记录，失败时静默处理
  async function remove(dbId: number, userId: number): Promise<void> {
    try {
      await deleteHistory(dbId, userId)
    } catch (e) {
      console.warn('[useHistoryDb] remove failed:', e)
    }
  }

  // 清空指定用户的所有历史记录，失败时静默处理
  async function clear(userId: number): Promise<void> {
    try {
      await clearHistory(userId)
    } catch (e) {
      console.warn('[useHistoryDb] clear failed:', e)
    }
  }

  return { load, persist, remove, clear }
}
