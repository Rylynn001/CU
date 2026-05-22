import { ref, onUnmounted } from 'vue'
import { getWsUrl } from '../config'
import { getImageUrl } from '../api/comfyui'
import { generateUUID } from '../utils/uuid'

/**
 * 管理与 ComfyUI 的 WebSocket 连接，监听生成进度和结果。
 * 仅用于直连本地 ComfyUI 的模式（非 API 代理模式）。
 */
export function useComfyWebSocket() {
  // 每个客户端唯一 id，提交 prompt 时一并传给 ComfyUI，用于过滤 WS 消息
  const clientId = generateUUID().replace(/-/g, '')
  const progress = ref(0)       // 当前生成进度 0-100
  const generating = ref(false) // 是否正在生成
  const imageUrl = ref('')      // 生成完成后的图片 URL
  const connected = ref(false)  // WebSocket 是否已连接

  let ws: WebSocket | null = null
  let currentPromptId = ''      // 当前正在监听的 prompt id
  let timeoutTimer: ReturnType<typeof setTimeout> | null = null

  // 建立 WebSocket 连接，监听进度/完成/执行消息
  function connect() {
    if (ws) ws.close()
    ws = new WebSocket(`${getWsUrl()}?clientId=${clientId}`)

    ws.onopen = () => { connected.value = true }
    ws.onclose = () => { connected.value = false }

    ws.onmessage = (event) => {
      if (typeof event.data !== 'string') return
      const msg = JSON.parse(event.data)
      console.log('[WS]', msg.type, msg.data)

      switch (msg.type) {
        case 'progress':
          // 更新当前 prompt 的采样进度
          if (msg.data.prompt_id === currentPromptId) {
            progress.value = Math.round((msg.data.value / msg.data.max) * 100)
          }
          break
        case 'executed':
          // 节点执行完毕，提取输出图片 URL
          if (msg.data.prompt_id === currentPromptId) {
            const output = msg.data.output
            if (output?.images?.length) {
              const img = output.images[0]
              imageUrl.value = getImageUrl(img.filename, img.subfolder || '', img.type || 'output')
              console.log('[WS] Image URL:', imageUrl.value)
            }
          }
          break
        case 'executing':
          // node === null 表示整个 prompt 执行完毕
          if (msg.data.prompt_id === currentPromptId && msg.data.node === null) {
            generating.value = false
            if (timeoutTimer) {
              clearTimeout(timeoutTimer)
              timeoutTimer = null
            }
          }
          break
        default:
          console.log('[WS] unhandled message type:', msg.type, msg)
      }
    }
  }

  // 开始监听指定 prompt 的生成进度，并设置 5 分钟超时保护
  function startGeneration(promptId: string) {
    currentPromptId = promptId
    progress.value = 0
    imageUrl.value = ''
    generating.value = true

    if (timeoutTimer) {
      clearTimeout(timeoutTimer)
    }

    // 5 分钟后若仍未完成，强制重置状态，避免界面卡住
    timeoutTimer = setTimeout(() => {
      console.warn('[WS] Generation timeout, resetting state')
      generating.value = false
      progress.value = 0
      timeoutTimer = null
    }, 300000)
  }

  // 断开连接并清理定时器
  function disconnect() {
    if (timeoutTimer) {
      clearTimeout(timeoutTimer)
      timeoutTimer = null
    }
    ws?.close()
    ws = null
  }

  // 组件卸载时自动断开
  onUnmounted(disconnect)

  return {
    clientId,
    progress,
    generating,
    imageUrl,
    connected,
    connect,
    startGeneration,
    disconnect,
  }
}
