import { pollTaskUntilDone } from '../api/apiService'

interface BaseRecord {
  id: string
  taskId?: string
  status: 'generating' | 'done' | 'error'
  errorMsg?: string
  dbId?: number
}

export type PollResultHandler<T extends BaseRecord> = (rec: T, result: {
  images: Array<{ url?: string }>
  historyId?: number
  inputAssetUrls?: Array<{ url: string; type: string }>
}) => void

/**
 * 通用任务轮询 composable。
 * 先查一次任务状态，若已完成直接处理结果；否则开始轮询直到完成。
 * 结果如何写回 record 由调用方通过 onDone 回调决定，保持灵活性。
 */
export function useTaskPolling<T extends BaseRecord>(
  getRecords: () => T[],
  saveRecords: () => void,
) {
  /**
   * 恢复对某个任务的轮询（页面刷新后调用）。
   * record: 需要恢复的记录
   * userId: 当前用户 id
   * onDone: 任务完成时的回调，负责将结果写入 record
   * expectedType: 期望的结果类型（image / video）
   */
  async function resumeTaskPolling(
    record: T,
    userId: number | undefined,
    onDone: PollResultHandler<T>,
    expectedType: 'image' | 'video' = 'image',
  ) {
    if (!record.taskId) return

    // 每次操作前重新从 records 中查找，避免持有过期引用
    const getRecord = () => getRecords().find(r => r.id === record.id)

    try {
      // 先查一次当前状态，避免任务已完成还走完整轮询
      const checkUrl = userId
        ? `/api/api-proxy/task/${record.taskId}?user_id=${userId}`
        : `/api/api-proxy/task/${record.taskId}`

      const checkRes = await fetch(checkUrl)
      if (checkRes.ok) {
        const checkData = await checkRes.json()
        if (checkData.status === 'completed' && checkData.result) {
          const rec = getRecord()
          if (rec) {
            onDone(rec, {
              images: checkData.result,
              historyId: checkData.history_id,
              inputAssetUrls: checkData.input_asset_urls,
            })
            rec.status = 'done'
            if (checkData.history_id) rec.dbId = checkData.history_id
            saveRecords()
          }
          return
        } else if (checkData.status === 'failed') {
          const rec = getRecord()
          if (rec) {
            rec.status = 'error'
            rec.errorMsg = checkData.error?.error_message || '任务失败'
            if (checkData.history_id) rec.dbId = checkData.history_id
            saveRecords()
          }
          return
        }
      }

      // 任务仍在进行中，开始完整轮询
      const result = await pollTaskUntilDone(record.taskId, userId, expectedType)
      const rec = getRecord()
      if (rec) {
        onDone(rec, {
          images: result.images,
          historyId: (result as any).historyId,
          inputAssetUrls: (result as any).inputAssetUrls,
        })
        rec.status = 'done'
        if ((result as any).historyId) rec.dbId = (result as any).historyId
      }
    } catch (e: any) {
      const rec = getRecord()
      if (rec) {
        rec.status = 'error'
        rec.errorMsg = e.message
        if (e.name === 'TaskFailedError' && e.historyId) rec.dbId = e.historyId
      }
    } finally {
      saveRecords()
    }
  }

  return { resumeTaskPolling }
}
