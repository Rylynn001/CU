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

export function useTaskHistory<T extends BaseRecord>(
  storageKey: string,
  maxRecords = 50,
  beforeSave?: (r: T) => Partial<T>,
) {
  function load(): T[] {
    try {
      const raw = localStorage.getItem(storageKey)
      return raw ? JSON.parse(raw) : []
    } catch {
      return []
    }
  }

  const records = ref<T[]>(load())

  function saveRecords() {
    try {
      const toSave = beforeSave
        ? (records.value as T[]).map(r => ({ ...r, ...beforeSave(r) }))
        : (records.value as T[])
      localStorage.setItem(storageKey, JSON.stringify(toSave.slice(0, maxRecords)))
    } catch {
      console.warn("localStorage quota exceeded, clearing old records")
      localStorage.removeItem(storageKey)
    }
  }

  function clearAll() {
    records.value = [] as any
    localStorage.removeItem(storageKey)
  }

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

  function formatTime(ts: number): string {
    const d = new Date(ts)
    const pad = (n: number) => String(n).padStart(2, "0")
    return d.getMonth() + 1 + "/" + d.getDate() + " " + pad(d.getHours()) + ":" + pad(d.getMinutes())
  }

  return { records, saveRecords, clearAll, formatTime, deleteRecord }
}
