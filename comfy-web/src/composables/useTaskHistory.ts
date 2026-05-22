import { ref } from 'vue'
import { cancelTask } from '../api/apiService'
import { getCurrentUserId } from '../utils/user'

interface BaseRecord {
  id: string
  status: string
  taskId?: string
  createdAt: number
  modelName: string
}

/**
 * 通用任务历史管理。
 * 负责从 localStorage 读写记录，以及删除时取消正在进行的任务。
 * storageKey: localStorage 的 key
 * maxRecords: 最多保留条数，超出时截断旧记录
 * beforeSave: 保存前对每条记录做转换（如清除大字段）
 */
export function useTaskHistory<T extends BaseRecord>(
  storageKey: string,
  maxRecords = 50,
  beforeSave?: (r: T) => Partial<T>,
) {
  // 从 localStorage 初始化记录
  function load(): T[] {
    try {
      const raw = localStorage.getItem(storageKey)
      return raw ? JSON.parse(raw) : []
    } catch {
      return []
    }
  }

  const records = ref<T[]>(load())

  // 将当前 records 持久化到 localStorage，超出 maxRecords 时截断
  function saveRecords() {
    try {
      const toSave = beforeSave
        ? (records.value as T[]).map(r => ({ ...r, ...beforeSave(r) }))
        : (records.value as T[])
      localStorage.setItem(storageKey, JSON.stringify(toSave.slice(0, maxRecords)))
    } catch {
      // 存储空间不足时清空，避免卡死
      console.warn("localStorage quota exceeded, clearing old records")
      localStorage.removeItem(storageKey)
    }
  }

  // 清空所有记录
  function clearAll() {
    records.value = [] as any
    localStorage.removeItem(storageKey)
  }

  // 删除单条记录；若任务正在生成中，先弹确认框并取消后端任务
  async function deleteRecord(id: string) {
    const record = (records.value as T[]).find(r => r.id === id)
    if (record && record.taskId && record.status === 'generating') {
      if (confirm('该任务正在生成中，确定要停止并删除吗？')) {
        await cancelTask(record.taskId, getCurrentUserId())
        records.value = (records.value as T[]).filter(r => r.id !== id) as any
        saveRecords()
      }
    } else {
      records.value = (records.value as T[]).filter(r => r.id !== id) as any
      saveRecords()
    }
  }

  // 将时间戳格式化为 "M/D HH:mm"
  function formatTime(ts: number): string {
    const d = new Date(ts)
    const pad = (n: number) => String(n).padStart(2, "0")
    return d.getMonth() + 1 + "/" + d.getDate() + " " + pad(d.getHours()) + ":" + pad(d.getMinutes())
  }

  return { records, saveRecords, clearAll, formatTime, deleteRecord }
}
