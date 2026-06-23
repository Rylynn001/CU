import { pollTaskUntilDone } from '../api/apiService'

// 单条持久化记录的结构
interface SbPendingTask {
  sbId: number
  taskId: string
  type: 'video' | 'frame'
  frameType?: 'first_frame' | 'last_frame'
  episodeId: number
}

const STORAGE_KEY = 'drama_sb_pending_tasks'

function loadTasks(): SbPendingTask[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

function saveTasks(tasks: SbPendingTask[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks))
}

export function addSbPendingTask(task: SbPendingTask) {
  const tasks = loadTasks().filter(
    t => !(t.sbId === task.sbId && t.type === task.type && t.frameType === task.frameType),
  )
  tasks.push(task)
  saveTasks(tasks)
}

export function removeSbPendingTask(sbId: number, type: 'video' | 'frame', frameType?: 'first_frame' | 'last_frame') {
  saveTasks(loadTasks().filter(
    t => !(t.sbId === sbId && t.type === type && t.frameType === frameType),
  ))
}

/**
 * 页面加载时调用，恢复当前 episode 未完成的任务。
 * onVideoDone / onFrameDone 负责把结果写回对应 sb 对象和后端。
 */
export async function resumeSbPendingTasks(
  episodeId: number,
  userId: number | undefined,
  onVideoDone: (sbId: number, videoUrl: string) => Promise<void>,
  onFrameDone: (sbId: number, frameType: 'first_frame' | 'last_frame', imgUrl: string, assetId: number) => Promise<void>,
) {
  const tasks = loadTasks().filter(t => t.episodeId === episodeId)
  if (!tasks.length) return

  await Promise.allSettled(tasks.map(async task => {
    try {
      if (task.type === 'video') {
        const result = await pollTaskUntilDone(task.taskId, userId, 'video')
        const item = result.images?.[0]
        if (item?.url) await onVideoDone(task.sbId, item.url)
      } else if (task.type === 'frame' && task.frameType) {
        const result = await pollTaskUntilDone(task.taskId, userId, 'image')
        const item = result.images?.[0]
        if (item?.url && item?.asset_id) await onFrameDone(task.sbId, task.frameType, item.url, item.asset_id)
      }
    } catch (_) {
      // 任务失败或已过期，静默移除
    } finally {
      removeSbPendingTask(task.sbId, task.type, task.frameType)
    }
  }))
}
