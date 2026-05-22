import { ref, computed } from 'vue'
import { useTaskHistory } from './useTaskHistory'
import { useHistoryDb } from './useHistoryDb'
import { getCurrentUserId } from '../utils/user'
import { generateUUID } from '../utils/uuid'
import type { HistoryRecord } from './useHistoryDb'

interface BaseGenerationRecord {
  id: string
  dbId?: number
  createdAt: number
  prompt: string
  modelName: string
  status: 'generating' | 'done' | 'error'
  progress: number
  taskId?: string
  mode: string
  errorMsg?: string
}

export function useGenerationHistory<T extends BaseGenerationRecord>(
  storageKey: string,
  historyType: 'img' | 'video',
  beforeSave?: (r: T) => Partial<T>,
) {
  const { records, saveRecords, clearAll: clearAllLocal, deleteRecord: deleteRecordLocal } =
    useTaskHistory<T>(storageKey, 50, beforeSave)

  const historyDb = useHistoryDb()
  const searchQuery = ref('')
  const expandedInputs = ref<Set<string>>(new Set())

  const filteredRecords = computed(() => {
    if (!searchQuery.value.trim()) return records.value as T[]
    const q = searchQuery.value.trim().toLowerCase()
    return (records.value as T[]).filter(r => r.prompt.toLowerCase().includes(q))
  })

  function toggleInputExpand(id: string) {
    if (expandedInputs.value.has(id)) expandedInputs.value.delete(id)
    else expandedInputs.value.add(id)
  }

  async function deleteRecord(id: string) {
    const rec = (records.value as T[]).find(r => r.id === id)
    if (rec?.dbId) {
      const userId = getCurrentUserId()
      if (userId) await historyDb.remove(rec.dbId, userId)
    }
    await deleteRecordLocal(id)
  }

  async function clearAll() {
    const userId = getCurrentUserId()
    if (userId) await historyDb.clear(userId)
    clearAllLocal()
  }

  /**
   * 从 DB 加载历史，合并到 records。
   * mapDbRecord: 将 HistoryRecord 转换为页面的 T 类型。
   * 返回 userId，供调用方继续使用。
   */
  async function loadFromDb(
    mapDbRecord: (r: HistoryRecord) => T,
  ): Promise<number | undefined> {
    const userId = getCurrentUserId()
    if (!userId) return undefined

    const dbRecords = await historyDb.load(userId, historyType)
    const localPending = (records.value as T[]).filter(r => r.status === 'generating')
    const fromDb = dbRecords.map(mapDbRecord)
    records.value = [...localPending, ...fromDb] as any
    saveRecords()
    return userId
  }

  /**
   * 标记刷新后无法恢复的任务为失败。
   * pendingFilter: 哪些 generating 任务需要恢复轮询（有 taskId 的）。
   * 返回需要恢复轮询的记录列表。
   */
  function markStaleRecords(mode?: string): T[] {
    const pending: T[] = []

    ;(records.value as T[]).forEach(r => {
      if (r.status !== 'generating') return
      if (r.taskId) {
        pending.push(r)
      } else if (!mode || r.mode === mode) {
        r.status = 'error'
        r.errorMsg = '页面刷新，结果已丢失'
      }
    })

    saveRecords()
    return pending
  }

  return {
    records,
    saveRecords,
    searchQuery,
    expandedInputs,
    filteredRecords,
    toggleInputExpand,
    deleteRecord,
    clearAll,
    loadFromDb,
    markStaleRecords,
    generateUUID,
  }
}
