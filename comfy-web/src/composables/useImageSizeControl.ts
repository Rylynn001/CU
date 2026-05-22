import { ref } from 'vue'

const ratios = [
  { label: '1:1',  w: 1,  h: 1,  icon: '⬜' },
  { label: '16:9', w: 16, h: 9,  icon: '▬' },
  { label: '9:16', w: 9,  h: 16, icon: '▮' },
  { label: '4:3',  w: 4,  h: 3,  icon: '▭' },
  { label: '3:4',  w: 3,  h: 4,  icon: '▯' },
]

const resolutions = [
  { label: '512',   base: 512 },
  { label: '768',   base: 768 },
  { label: '1024',  base: 1024 },
  { label: '1080p', base: 1920 },
]

export function useImageSizeControl(
  getSize: () => { width: number; height: number },
  setSize: (w: number, h: number) => void,
) {
  const activeRatio = ref(ratios[0])
  const activeResolution = ref(resolutions[0])
  const ratioOpen = ref(false)
  const sizeCustomized = ref(false)

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

  function setRatio(r: typeof ratios[0]) {
    activeRatio.value = r
    applyRatioAndRes()
  }

  function setResolution(r: typeof resolutions[0]) {
    activeResolution.value = r
    applyRatioAndRes()
  }

  let stepTimer: ReturnType<typeof setTimeout> | null = null
  let stepInterval: ReturnType<typeof setInterval> | null = null

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

  function startStep(field: 'width' | 'height', delta: number) {
    applyStep(field, delta)
    stepTimer = setTimeout(() => {
      stepInterval = setInterval(() => applyStep(field, delta), 80)
    }, 500)
  }

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
