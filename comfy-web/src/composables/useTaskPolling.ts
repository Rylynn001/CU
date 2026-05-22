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
}) => void

/**
 * 通用任务轮询。先查一次状态，若已完成直接处理；否则开始轮询。
 * 结果如何写回 record 由调用方通过 onDone 回调决定。
 */
export function useTaskPolling<T extends BaseRecord>(
  getRecords: () => T[],
  saveRecords: () => void,
) {
  async function resumeTaskPolling(
    record: T,
    userId: number | undefined,
    onDone: PollResultHandler<T>,
    expectedType: 'image' | 'video' = 'image',
  ) {
    if (!record.taskId) return

    const getRecord = () => getRecords().find(r => r.id === record.id)

    try {
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
            saveRecords()
          }
          return
        }
      }

      const result = await pollTaskUntilDone(record.taskId, userId, expectedType)
      const rec = getRecord()
      if (rec) {
        onDone(rec, {
          images: result.images,
          historyId: (result as any).historyId,
        })
        rec.status = 'done'
        if ((result as any).historyId) rec.dbId = (result as any).historyId
      }
    } catch (e: any) {
      const rec = getRecord()
      if (rec) {
        rec.status = 'error'
        rec.errorMsg = e.message
      }
    } finally {
      saveRecords()
    }
  }

  return { resumeTaskPolling }
}
