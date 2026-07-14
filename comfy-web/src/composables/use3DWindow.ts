import { reactive } from 'vue'

type CaptureHandler = (file: File) => void

const state = reactive({
  open: false,
  minimized: false,
  maximized: false,
  title: '3D 取景',
  saveState: '未保存' as '未保存' | '保存中' | '已保存' | '保存失败',
})

let captureHandler: CaptureHandler | null = null

export function use3DWindow() {
  function open3DWindow(handler: CaptureHandler) {
    captureHandler = handler
    state.open = true
    state.minimized = false
  }

  function close3DWindow() { state.open = false; captureHandler = null }
  function deliverCapture(file: File) { captureHandler?.(file) }

  return { state, open3DWindow, close3DWindow, deliverCapture }
}
