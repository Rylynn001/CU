import { saveHistory, fetchHistory, deleteHistory, clearHistory, type HistoryRecord } from '../api/apiService'

export type { HistoryRecord }

/**
 * 封装历史记录的数据库操作。
 * 视图层负责将 DB 记录合并到本地 records 中，
 * 本 composable 只负责与后端通信。
 */
export function useHistoryDb() {
  async function load(userId: number): Promise<HistoryRecord[]> {
    try {
      return await fetchHistory(userId)
    } catch (e) {
      console.warn('[useHistoryDb] load failed:', e)
      return []
    }
  }

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

  async function remove(dbId: number, userId: number): Promise<void> {
    try {
      await deleteHistory(dbId, userId)
    } catch (e) {
      console.warn('[useHistoryDb] remove failed:', e)
    }
  }

  async function clear(userId: number): Promise<void> {
    try {
      await clearHistory(userId)
    } catch (e) {
      console.warn('[useHistoryDb] clear failed:', e)
    }
  }

  return { load, persist, remove, clear }
}
