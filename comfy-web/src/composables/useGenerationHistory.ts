import { ref, computed } from 'vue'
import { useTaskHistory } from './useTaskHistory'
import { useHistoryDb } from './useHistoryDb'
import { getCurrentUserId } from '../utils/user'
import { generateUUID } from '../utils/uuid'
import type { HistoryRecord } from './useHistoryDb'

interface BaseGenerationRecord {
  id: string
  dbId?: number        // 后端数据库中的记录 id，用于删除/更新
  createdAt: number
  prompt: string
  modelName: string
  status: 'generating' | 'done' | 'error'
  progress: number
  taskId?: string      // 异步任务 id，有值时可恢复轮询
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

  // 分页状态
  const dbPage = ref(1)
  const dbPageSize = ref<30 | 50 | 100>(30)
  const dbTotal = ref(0)
  const hasMoreInDb = computed(() => {
    const loaded = (dbPage.value) * dbPageSize.value
    return loaded < dbTotal.value
  })

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
    dbPage.value = 1
    dbTotal.value = 0
  }

  async function loadFromDb(
    mapDbRecord: (r: HistoryRecord) => T,
    filter?: (r: HistoryRecord) => boolean,
  ): Promise<number | undefined> {
    const userId = getCurrentUserId()
    if (!userId) return undefined

    dbPage.value = 1
    const { records: dbRecords, total } = await historyDb.load(userId, historyType, 1, dbPageSize.value)
    dbTotal.value = total
    const filtered = filter ? dbRecords.filter(filter) : dbRecords
    const localPending = (records.value as T[]).filter(r => r.status === 'generating')
    const fromDb = filtered.map(mapDbRecord)
    records.value = [...localPending, ...fromDb] as any
    saveRecords()
    return userId
  }

  async function loadMoreFromDb(
    mapDbRecord: (r: HistoryRecord) => T,
    filter?: (r: HistoryRecord) => boolean,
  ): Promise<void> {
    const userId = getCurrentUserId()
    if (!userId || !hasMoreInDb.value) return

    const nextPage = dbPage.value + 1
    const { records: dbRecords, total } = await historyDb.load(userId, historyType, nextPage, dbPageSize.value)
    dbTotal.value = total
    dbPage.value = nextPage
    const filtered = filter ? dbRecords.filter(filter) : dbRecords
    const fromDb = filtered.map(mapDbRecord)
    ;(records.value as T[]).push(...(fromDb as any[]))
    saveRecords()
  }

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
    loadMoreFromDb,
    hasMoreInDb,
    dbPageSize,
    dbTotal,
    markStaleRecords,
    generateUUID,
  }
}
