<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { Canvas, Image as FabricImage, PencilBrush, Rect, IText } from 'fabric'

const props = defineProps<{
  imageSrc: string
  visible: boolean
  confirmLabel?: string
  generateLabel?: string
  inline?: boolean
}>()

const emit = defineEmits<{
  (e: 'confirm', file: File): void
  (e: 'cancel'): void
  (e: 'generate', file: File): void
}>()

const canvasEl = ref<HTMLCanvasElement | null>(null)
let canvas: Canvas | null = null

type Tool = 'select' | 'brush' | 'rect' | 'text'
const activeTool = ref<Tool>('brush')
const brushSize = ref(6)
const brushColor = ref('#ff3b3b')
const fillColor = ref('transparent')

function setTool(tool: Tool) {
  activeTool.value = tool
  if (!canvas) return
  if (tool === 'brush') {
    canvas.isDrawingMode = true
    const brush = new PencilBrush(canvas)
    brush.color = brushColor.value
    brush.width = brushSize.value
    canvas.freeDrawingBrush = brush
  } else {
    canvas.isDrawingMode = false
  }
}

watch(brushColor, (c) => {
  if (canvas?.freeDrawingBrush) canvas.freeDrawingBrush.color = c
})
watch(brushSize, (s) => {
  if (canvas?.freeDrawingBrush) (canvas.freeDrawingBrush as PencilBrush).width = s
})

// 矩形绘制状态
let isDrawingRect = false
let rectStartX = 0
let rectStartY = 0
let activeRect: Rect | null = null

function onMouseDown(opt: any) {
  if (activeTool.value !== 'rect') return
  const pointer = canvas!.getScenePoint(opt.e)
  isDrawingRect = true
  rectStartX = pointer.x
  rectStartY = pointer.y
  activeRect = new Rect({
    left: rectStartX,
    top: rectStartY,
    width: 0,
    height: 0,
    fill: fillColor.value === 'transparent' ? 'transparent' : fillColor.value,
    stroke: brushColor.value,
    strokeWidth: brushSize.value,
    selectable: true,
  })
  canvas!.add(activeRect)
}

function onMouseMove(opt: any) {
  if (!isDrawingRect || !activeRect) return
  const pointer = canvas!.getScenePoint(opt.e)
  const w = pointer.x - rectStartX
  const h = pointer.y - rectStartY
  activeRect.set({
    left: w < 0 ? pointer.x : rectStartX,
    top: h < 0 ? pointer.y : rectStartY,
    width: Math.abs(w),
    height: Math.abs(h),
  })
  canvas!.renderAll()
}

function onMouseUp() {
  if (!isDrawingRect) return
  isDrawingRect = false
  activeRect = null
}

function addText() {
  if (!canvas) return
  const text = new IText('双击编辑', {
    left: 80,
    top: 80,
    fontSize: 24,
    fill: brushColor.value,
    fontFamily: 'Arial',
  })
  canvas.add(text)
  canvas.setActiveObject(text)
  activeTool.value = 'select'
  canvas.isDrawingMode = false
}

function undo() {
  if (!canvas) return
  const objs = canvas.getObjects()
  if (objs.length > 1) {
    canvas.remove(objs[objs.length - 1])
    canvas.renderAll()
  }
}

function clearAll() {
  if (!canvas) return
  const objs = canvas.getObjects()
  // 保留第一个（背景图）
  for (let i = objs.length - 1; i >= 1; i--) {
    canvas.remove(objs[i])
  }
  canvas.renderAll()
}

async function initCanvas() {
  if (!canvasEl.value) return
  if (canvas) {
    canvas.dispose()
    canvas = null
  }

  const img = new window.Image()
  img.crossOrigin = 'anonymous'
  img.onload = () => {
    const maxW = Math.min(window.innerWidth * 0.85, 900)
    const maxH = window.innerHeight * 0.65
    const scale = Math.min(maxW / img.width, maxH / img.height, 1)
    const w = Math.round(img.width * scale)
    const h = Math.round(img.height * scale)

    canvasEl.value!.width = w
    canvasEl.value!.height = h

    canvas = new Canvas(canvasEl.value!, { width: w, height: h })

    const fabricImg = new FabricImage(img, {
      scaleX: scale,
      scaleY: scale,
      selectable: false,
      evented: false,
    })
    canvas.add(fabricImg)
    canvas.renderAll()

    canvas.on('mouse:down', onMouseDown)
    canvas.on('mouse:move', onMouseMove)
    canvas.on('mouse:up', onMouseUp)

    setTool('brush')
  }
  img.src = props.imageSrc
}

watch(() => props.visible, (v) => {
  if (v) setTimeout(initCanvas, 50)
})

onMounted(() => {
  if (props.visible) initCanvas()
})

onBeforeUnmount(() => {
  canvas?.dispose()
})

function confirm() {
  if (!canvas) return
  const dataUrl = canvas.toDataURL({ format: 'png', multiplier: 1 })
  fetch(dataUrl)
    .then(r => r.blob())
    .then(blob => {
      const file = new File([blob], 'edited.png', { type: 'image/png' })
      emit('confirm', file)
    })
}

function confirmAndGenerate() {
  if (!canvas) return
  const dataUrl = canvas.toDataURL({ format: 'png', multiplier: 1 })
  fetch(dataUrl)
    .then(r => r.blob())
    .then(blob => {
      const file = new File([blob], 'edited.png', { type: 'image/png' })
      emit('generate', file)
    })
}

async function getFile(): Promise<File | null> {
  if (!canvas) return null
  const dataUrl = canvas.toDataURL({ format: 'png', multiplier: 1 })
  const res = await fetch(dataUrl)
  const blob = await res.blob()
  return new File([blob], 'edited.png', { type: 'image/png' })
}

defineExpose({ getFile })
</script>

<template>
  <!-- 内联模式：直接渲染工具栏+画布，无遮罩 -->
  <div v-if="visible && inline" class="editor-box editor-inline">
    <div class="editor-toolbar">
        <!-- 工具选择 -->
        <div class="tool-group">
          <button :class="['tool-btn', { active: activeTool === 'brush' }]" @click="setTool('brush')" title="画笔">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19l7-7-3-3-7 7v3h3z"/><path d="M18 13l1.5-1.5a2.12 2.12 0 0 0-3-3L15 10"/></svg>
          </button>
          <button :class="['tool-btn', { active: activeTool === 'rect' }]" @click="setTool('rect')" title="矩形">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
          </button>
          <button class="tool-btn" @click="addText(); setTool('select')" title="文字">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7V4h16v3"/><path d="M9 20h6"/><path d="M12 4v16"/></svg>
          </button>
          <button :class="['tool-btn', { active: activeTool === 'select' }]" @click="setTool('select')" title="选择">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 3l14 9-7 1-4 7z"/></svg>
          </button>
        </div>
        <div class="divider-v" />
        <label class="color-pick" title="颜色">
          <input type="color" v-model="brushColor" @input="setTool(activeTool)" />
          <span class="color-dot" :style="{ background: brushColor }" />
        </label>
        <div class="size-group">
          <span class="size-label">{{ brushSize }}px</span>
          <input type="range" v-model.number="brushSize" min="1" max="40" class="size-slider" />
        </div>
        <div class="divider-v" />
        <button class="tool-btn" @click="undo" title="撤销">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7v6h6"/><path d="M3 13A9 9 0 1 0 6 6.7L3 13"/></svg>
        </button>
        <button class="tool-btn" @click="clearAll" title="清除标注">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>
        </button>
    </div>
    <div class="canvas-wrap canvas-wrap-inline">
      <canvas ref="canvasEl" />
    </div>
  </div>

  <!-- 弹窗模式 -->
  <div v-else-if="visible" class="editor-overlay" @click.self="emit('cancel')">
    <div class="editor-box">
      <div class="editor-toolbar">
        <!-- 工具选择 -->
        <div class="tool-group">
          <button :class="['tool-btn', { active: activeTool === 'brush' }]" @click="setTool('brush')" title="画笔">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19l7-7-3-3-7 7v3h3z"/><path d="M18 13l1.5-1.5a2.12 2.12 0 0 0-3-3L15 10"/></svg>
          </button>
          <button :class="['tool-btn', { active: activeTool === 'rect' }]" @click="setTool('rect')" title="矩形">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
          </button>
          <button class="tool-btn" @click="addText(); setTool('select')" title="文字">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7V4h16v3"/><path d="M9 20h6"/><path d="M12 4v16"/></svg>
          </button>
          <button :class="['tool-btn', { active: activeTool === 'select' }]" @click="setTool('select')" title="选择">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 3l14 9-7 1-4 7z"/></svg>
          </button>
        </div>

        <div class="divider-v" />

        <!-- 颜色 -->
        <label class="color-pick" title="颜色">
          <input type="color" v-model="brushColor" @input="setTool(activeTool)" />
          <span class="color-dot" :style="{ background: brushColor }" />
        </label>

        <!-- 笔刷大小 -->
        <div class="size-group">
          <span class="size-label">{{ brushSize }}px</span>
          <input type="range" v-model.number="brushSize" min="1" max="40" class="size-slider" />
        </div>

        <div class="divider-v" />

        <!-- 操作 -->
        <button class="tool-btn" @click="undo" title="撤销">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7v6h6"/><path d="M3 13A9 9 0 1 0 6 6.7L3 13"/></svg>
        </button>
        <button class="tool-btn" @click="clearAll" title="清除标注">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>
        </button>

        <div style="flex:1" />

        <button class="action-btn cancel" @click="emit('cancel')">取消</button>
        <button class="action-btn confirm" @click="confirm">{{ props.confirmLabel ?? '使用此图' }}</button>
        <button v-if="props.generateLabel" class="action-btn generate" @click="confirmAndGenerate">{{ props.generateLabel }}</button>
      </div>

      <div class="canvas-wrap">
        <canvas ref="canvasEl" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.75);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.editor-box {
  background: transparent;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  max-width: 95vw;
  max-height: 95vh;
}

.editor-inline {
  flex: 1;
  min-width: 0;
  border-radius: 12px;
  max-width: none;
  max-height: none;
  height: 100%;
}

.canvas-wrap-inline {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  background: transparent;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  background: rgba(255,255,255,0.04);
  border-bottom: 1px solid rgba(255,255,255,0.08);
  flex-wrap: wrap;
}

.tool-group {
  display: flex;
  gap: 4px;
}

.tool-btn {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.1);
  background: transparent;
  color: rgba(255,255,255,0.6);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.tool-btn:hover { background: rgba(255,255,255,0.08); color: white; }
.tool-btn.active { background: rgba(108,99,255,0.4); border-color: rgba(108,99,255,0.7); color: white; }

.divider-v {
  width: 1px;
  height: 24px;
  background: rgba(255,255,255,0.1);
  margin: 0 4px;
}

.color-pick {
  cursor: pointer;
  position: relative;
}
.color-pick input[type=color] {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.color-dot {
  display: block;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.3);
}

.size-group {
  display: flex;
  align-items: center;
  gap: 6px;
}
.size-label {
  font-size: 12px;
  color: rgba(255,255,255,0.5);
  min-width: 30px;
}
.size-slider {
  width: 80px;
  accent-color: #6c63ff;
}

.action-btn {
  padding: 6px 16px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}
.action-btn.cancel {
  background: rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.7);
}
.action-btn.cancel:hover { background: rgba(255,255,255,0.14); }
.action-btn.confirm {
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  color: white;
}
.action-btn.confirm:hover { opacity: 0.9; }

.action-btn.generate {
  background: linear-gradient(135deg, #6c63ff, #a78bfa, #6c63ff);
  background-size: 200% auto;
  color: white;
  animation: shimmer 3s linear infinite;
}
.action-btn.generate:hover { opacity: 0.9; transform: translateY(-1px); }

@keyframes shimmer {
  0% { background-position: 0% center; }
  100% { background-position: 200% center; }
}

.canvas-wrap {
  overflow: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: transparent;
}
</style>
