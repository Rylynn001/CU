import { ref } from 'vue'
import type { HistoryRecord } from '../api/apiService'

// 全局单例：跨页面（资产侧边栏 → 生成页）传递"待定位"的历史记录
const pendingRecord = ref<HistoryRecord | null>(null)

/**
 * 跨页面定位历史记录。
 * 资产库右键"定位历史记录"时调用 requestLocateHistory 写入目标记录，
 * 目标页面（文生图/文生视频）通过 consumePendingLocate 取出并执行滚动+高亮。
 */
export function useLocateHistory() {
  function requestLocateHistory(record: HistoryRecord) {
    pendingRecord.value = record
  }

  function consumePendingLocate(): HistoryRecord | null {
    const record = pendingRecord.value
    pendingRecord.value = null
    return record
  }

  return { pendingRecord, requestLocateHistory, consumePendingLocate }
}
