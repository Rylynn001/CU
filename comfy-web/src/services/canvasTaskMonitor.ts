import { ElMessage } from 'element-plus'
import { authFetch, getCanvas } from '../api/apiService'
import type { CanvasNode } from './canvasGraph'

type Board = Awaited<ReturnType<typeof getCanvas>>
type TrackedCanvas = { name: string; pending: Set<string>; reported: Set<string> }
const canvases = new Map<number, TrackedCanvas>()
const listeners = new Set<(board: Board) => void>()
const polling = new Map<number, Promise<Board>>()
let activeCanvasId: number | undefined
let timer: ReturnType<typeof setInterval> | undefined
let session = 0

export function trackCanvasTasks(id: number, name: string, nodes: CanvasNode[]) {
  const tracked = canvases.get(id) ?? { name, pending: new Set<string>(), reported: new Set<string>() }
  tracked.name = name
  const pending = new Set<string>()
  for (const node of nodes) {
    const task = node.data.task
    if (!task) continue
    const key = node.data.executionId || task.taskId
    if (task.state === 'pending') pending.add(key)
    else if (tracked.pending.has(key) && !tracked.reported.has(key)) {
      tracked.reported.add(key)
      if (task.state === 'completed') ElMessage.success(`${name} · ${node.data.label}已完成`)
      else if (task.state === 'failed') ElMessage.error(`${name} · ${node.data.label}失败：${task.error || '生成失败'}`)
    }
  }
  tracked.pending = pending
  canvases.set(id, tracked)
}

export function setActiveCanvas(id?: number) { activeCanvasId = id }
export function forgetCanvasTasks(id: number) { canvases.delete(id) }
export function subscribeCanvasTasks(listener: (board: Board) => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function refreshCanvasTasks(id: number): Promise<Board> {
  const current = polling.get(id)
  if (current) return current
  const currentSession = session
  const operation = (async () => {
    let board = await getCanvas(id)
    if (currentSession !== session) return board
    trackCanvasTasks(id, board.name, board.document.nodes as unknown as CanvasNode[])
    // 沿用任务接口推进视频查询；排队步骤尚无真实任务编号，不能请求 /task。
    const tasks = (board.document.nodes as unknown as CanvasNode[])
      .map(node => node.data.task).filter(task => task?.state === 'pending' && task.historyId)
    const results = await Promise.allSettled(tasks.map(async task => {
      const response = await authFetch(`/api/api-proxy/task/${task!.taskId}`)
      if (!response.ok) return false
      const result = await response.json()
      return result.status === 'completed' || result.status === 'failed'
    }))
    if (currentSession !== session) return board
    if (results.some(result => result.status === 'fulfilled' && result.value)) board = await getCanvas(id)
    if (currentSession !== session) return board
    trackCanvasTasks(id, board.name, board.document.nodes as unknown as CanvasNode[])
    for (const listener of listeners) listener(board)
    return board
  })()
  polling.set(id, operation)
  void operation.finally(() => { if (polling.get(id) === operation) polling.delete(id) }).catch(() => {})
  return operation
}

export function startCanvasTaskMonitor() {
  if (timer !== undefined) return
  // 定时器属于应用根组件，切换页面只移除画布订阅，不停止任务跟踪。
  timer = setInterval(() => {
    for (const [id, canvas] of canvases) {
      if (id === activeCanvasId || canvas.pending.size) void refreshCanvasTasks(id).catch(() => {})
    }
  }, 3000)
}

export function stopCanvasTaskMonitor() {
  clearInterval(timer)
  timer = undefined
  session += 1
  activeCanvasId = undefined
  canvases.clear()
  polling.clear()
}
