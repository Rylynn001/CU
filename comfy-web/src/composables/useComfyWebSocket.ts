import { ref, onUnmounted } from 'vue'
import { getWsUrl } from '../config'
import { getImageUrl } from '../api/comfyui'

export function useComfyWebSocket() {
  const clientId = crypto.randomUUID().replace(/-/g, '')
  const progress = ref(0)
  const generating = ref(false)
  const imageUrl = ref('')
  const connected = ref(false)

  let ws: WebSocket | null = null
  let currentPromptId = ''
  let timeoutTimer: ReturnType<typeof setTimeout> | null = null

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
          if (msg.data.prompt_id === currentPromptId) {
            progress.value = Math.round((msg.data.value / msg.data.max) * 100)
          }
          break
        case 'executed':
          if (msg.data.prompt_id === currentPromptId) {
            // output 可能在 msg.data.output 里
            const output = msg.data.output
            if (output?.images?.length) {
              const img = output.images[0]
              imageUrl.value = getImageUrl(img.filename, img.subfolder || '', img.type || 'output')
              console.log('[WS] Image URL:', imageUrl.value)
            }
          }
          break
        case 'executing':
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

  function startGeneration(promptId: string) {
    currentPromptId = promptId
    progress.value = 0
    imageUrl.value = ''
    generating.value = true

    // 清除旧的超时
    if (timeoutTimer) {
      clearTimeout(timeoutTimer)
    }

    // 5 分钟超时保护
    timeoutTimer = setTimeout(() => {
      console.warn('[WS] Generation timeout, resetting state')
      generating.value = false
      progress.value = 0
      timeoutTimer = null
    }, 300000)
  }

  function disconnect() {
    if (timeoutTimer) {
      clearTimeout(timeoutTimer)
      timeoutTimer = null
    }
    ws?.close()
    ws = null
  }

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
