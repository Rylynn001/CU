import { ref } from 'vue'

// 预设比例列表
const ratios = [
  { label: '1:1',  w: 1,  h: 1,  icon: '⬜' },
  { label: '16:9', w: 16, h: 9,  icon: '▬' },
  { label: '9:16', w: 9,  h: 16, icon: '▮' },
  { label: '4:3',  w: 4,  h: 3,  icon: '▭' },
  { label: '3:4',  w: 3,  h: 4,  icon: '▯' },
]

// 预设分辨率列表（base 为长边像素数）
const resolutions = [
  { label: '512',   base: 512 },
  { label: '768',   base: 768 },
  { label: '1024',  base: 1024 },
  { label: '1080p', base: 1920 },
]

/**
 * 管理图片尺寸和比例控制。
 * 根据选中的比例和分辨率自动计算宽高（对齐到 8 的倍数，ComfyUI 要求）。
 * 也支持手动步进调整宽高（长按加速）。
 * getSize/setSize: 读写当前宽高，由调用方提供
 */
export function useImageSizeControl(
  getSize: () => { width: number; height: number },
  setSize: (w: number, h: number) => void,
) {
  const activeRatio = ref(ratios[0])
  const activeResolution = ref(resolutions[0])
  const ratioOpen = ref(false)       // 比例下拉是否展开
  const sizeCustomized = ref(false)  // 是否已手动修改过尺寸（用于 UI 提示）

  // 根据当前比例和分辨率计算并应用宽高，结果对齐到 8 的倍数
  function applyRatioAndRes() {
    const { w, h } = activeRatio.value
    const base = activeResolution.value.base
    let width: number, height: number
    if (w >= h) {
      width  = Math.round(base / 8) * 8
      height = Math.round(base * h / w / 8) * 8
    } else {
      height = Math.round(base / 8) * 8
      width  = Math.round(base * w / h / 8) * 8
    }
    setSize(width, height)
    sizeCustomized.value = false
  }

  // 切换比例并重新计算尺寸
  function setRatio(r: typeof ratios[0]) {
    activeRatio.value = r
    applyRatioAndRes()
  }

  // 切换分辨率并重新计算尺寸
  function setResolution(r: typeof resolutions[0]) {
    activeResolution.value = r
    applyRatioAndRes()
  }

  let stepTimer: ReturnType<typeof setTimeout> | null = null
  let stepInterval: ReturnType<typeof setInterval> | null = null

  // 单步调整宽或高，范围限制在 16-2048
  function applyStep(field: 'width' | 'height', delta: number) {
    const { width, height } = getSize()
    const val = field === 'width' ? width : height
    const next = Math.min(2048, Math.max(16, val + delta))
    setSize(
      field === 'width' ? next : width,
      field === 'height' ? next : height,
    )
    sizeCustomized.value = true
  }

  // 按住按钮时：立即执行一次，500ms 后开始每 80ms 连续执行（长按加速）
  function startStep(field: 'width' | 'height', delta: number) {
    applyStep(field, delta)
    stepTimer = setTimeout(() => {
      stepInterval = setInterval(() => applyStep(field, delta), 80)
    }, 500)
  }

  // 松开按钮时清除定时器
  function stopStep() {
    if (stepTimer) { clearTimeout(stepTimer); stepTimer = null }
    if (stepInterval) { clearInterval(stepInterval); stepInterval = null }
  }

  return {
    ratios,
    resolutions,
    activeRatio,
    activeResolution,
    ratioOpen,
    sizeCustomized,
    setRatio,
    setResolution,
    startStep,
    stopStep,
    applyStep,
  }
}
