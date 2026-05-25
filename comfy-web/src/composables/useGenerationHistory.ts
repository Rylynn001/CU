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

/**
 * 通用生成历史管理，图片和视频页面共用。
 * 在 useTaskHistory（本地存储）基础上叠加数据库同步能力。
 * storageKey: localStorage key
 * historyType: 'img' 或 'video'，用于过滤数据库记录
 * beforeSave: 保存前对记录做转换（如清除 base64 图片数据）
 */
export function useGenerationHistory<T extends BaseGenerationRecord>(
  storageKey: string,
  historyType: 'img' | 'video',
  beforeSave?: (r: T) => Partial<T>,
) {
  const { records, saveRecords, clearAll: clearAllLocal, deleteRecord: deleteRecordLocal } =
    useTaskHistory<T>(storageKey, 50, beforeSave)

  const historyDb = useHistoryDb()
  const searchQuery = ref('')
  // 记录哪些条目展开了输入内容区域
  const expandedInputs = ref<Set<string>>(new Set())

  // 按提示词关键字过滤记录
  const filteredRecords = computed(() => {
    if (!searchQuery.value.trim()) return records.value as T[]
    const q = searchQuery.value.trim().toLowerCase()
    return (records.value as T[]).filter(r => r.prompt.toLowerCase().includes(q))
  })

  // 切换某条记录的输入内容展开/折叠状态
  function toggleInputExpand(id: string) {
    if (expandedInputs.value.has(id)) expandedInputs.value.delete(id)
    else expandedInputs.value.add(id)
  }

  // 删除记录：若有 dbId 则同步删除后端数据库，再删本地
  async function deleteRecord(id: string) {
    const rec = (records.value as T[]).find(r => r.id === id)
    if (rec?.dbId) {
      const userId = getCurrentUserId()
      if (userId) await historyDb.remove(rec.dbId, userId)
    }
    await deleteRecordLocal(id)
  }

  // 清空所有记录：同步清空后端数据库和本地存储
  async function clearAll() {
    const userId = getCurrentUserId()
    if (userId) await historyDb.clear(userId)
    clearAllLocal()
  }

  /**
   * 从数据库加载历史，合并到本地 records。
   * 加载后本地 generating 中的任务保留在最前面（等待恢复轮询）。
   * mapDbRecord: 将后端 HistoryRecord 转换为页面使用的 T 类型。
   * 返回 userId，供调用方继续使用。
   */
  async function loadFromDb(
    mapDbRecord: (r: HistoryRecord) => T,
    filter?: (r: HistoryRecord) => boolean,
  ): Promise<number | undefined> {
    const userId = getCurrentUserId()
    if (!userId) return undefined

    const dbRecords = await historyDb.load(userId, historyType)
    const filtered = filter ? dbRecords.filter(filter) : dbRecords
    // 保留本地还在生成中的任务（刷新后需要恢复轮询）
    const localPending = (records.value as T[]).filter(r => r.status === 'generating')
    const fromDb = filtered.map(mapDbRecord)
    records.value = [...localPending, ...fromDb] as any
    saveRecords()
    return userId
  }

  /**
   * 页面刷新后处理遗留的 generating 任务：
   * - 有 taskId 的：加入返回列表，由调用方恢复轮询
   * - 无 taskId 的（本地 ComfyUI 模式）：标记为失败，结果已无法恢复
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
