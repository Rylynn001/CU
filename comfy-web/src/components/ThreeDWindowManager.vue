<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, reactive } from 'vue'
import { use3DWindow } from '../composables/use3DWindow'

const ModelViewer = defineAsyncComponent(() => import('./ModelViewer.vue'))
const { state, close3DWindow, deliverCapture } = use3DWindow()
const MIN_W = 720
const MIN_H = 480
const saved = (() => { try { return JSON.parse(localStorage.getItem('3d-window-rect') || 'null') } catch { return null } })()
const rect = reactive(saved || { x: Math.max(16, (innerWidth - 1040) / 2), y: Math.max(32, (innerHeight - 720) / 2), w: 1040, h: 720 })
let drag: { mode: string; sx: number; sy: number; start: typeof rect } | null = null

const mobile = computed(() => innerWidth < 760)
const style = computed(() => state.maximized || mobile.value
  ? { left:'0', top:'0', width:'100vw', height:'100vh' }
  : { left:`${rect.x}px`, top:`${rect.y}px`, width:`${rect.w}px`, height:`${rect.h}px` })

function begin(event: PointerEvent, mode: string) {
  if (state.maximized || mobile.value) return
  drag = { mode, sx:event.clientX, sy:event.clientY, start:{ ...rect } }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', end)
}

function move(event: PointerEvent) {
  if (!drag) return
  const dx = event.clientX - drag.sx, dy = event.clientY - drag.sy, s = drag.start
  if (drag.mode === 'move') { rect.x = Math.max(0, Math.min(innerWidth - 120, s.x + dx)); rect.y = Math.max(0, Math.min(innerHeight - 48, s.y + dy)); return }
  if (drag.mode.includes('e')) rect.w = Math.max(MIN_W, Math.min(innerWidth - s.x, s.w + dx))
  if (drag.mode.includes('s')) rect.h = Math.max(MIN_H, Math.min(innerHeight - s.y, s.h + dy))
  if (drag.mode.includes('w')) { const w=Math.max(MIN_W,s.w-dx); rect.x=s.x+s.w-w; rect.w=w }
  if (drag.mode.includes('n')) { const h=Math.max(MIN_H,s.h-dy); rect.y=s.y+s.h-h; rect.h=h }
}

function end() {
  drag = null
  localStorage.setItem('3d-window-rect', JSON.stringify(rect))
  window.removeEventListener('pointermove', move)
  window.removeEventListener('pointerup', end)
}

onBeforeUnmount(end)
</script>

<template>
  <div v-if="state.open && !state.minimized" class="window" :class="{ maximized: state.maximized }" :style="style">
    <header class="titlebar" @pointerdown="begin($event, 'move')">
      <div><strong>{{ state.title }}</strong><span>单帧参考</span></div>
      <nav @pointerdown.stop>
        <button title="最小化" @click="state.minimized = true">—</button>
        <button title="最大化" @click="state.maximized = !state.maximized">{{ state.maximized ? '❐' : '□' }}</button>
        <button title="关闭" @click="close3DWindow">×</button>
      </nav>
    </header>
    <div class="viewer"><ModelViewer windowed :visible="true" @update:visible="v => { if (!v) close3DWindow() }" @capture="deliverCapture" /></div>
    <i v-for="edge in ['n','ne','e','se','s','sw','w','nw']" :key="edge" class="resize" :class="edge" @pointerdown="begin($event, edge)" />
  </div>
  <button v-if="state.open && state.minimized" class="dock" @click="state.minimized = false"><span>3D</span>{{ state.title }}</button>
</template>

<style scoped>
.window{position:fixed;z-index:8000;min-width:720px;min-height:480px;overflow:hidden;border:1px solid var(--color-border);border-radius:10px;background:#080b11;box-shadow:0 24px 70px rgba(0,0,0,.55)}
.window.maximized{border:0;border-radius:0}.titlebar{height:42px;padding-left:14px;display:flex;align-items:center;justify-content:space-between;background:#0c0f16;border-bottom:1px solid var(--color-border);cursor:move;user-select:none}.titlebar>div{display:flex;align-items:center;gap:10px}.titlebar strong{font-size:12px;font-weight:500}.titlebar span{font-size:9px;color:var(--color-faint)}.titlebar span.已保存{color:var(--color-success)}.titlebar span.保存失败{color:var(--color-danger)}nav{height:100%;display:flex}nav button{width:42px;border:0;background:transparent;color:var(--color-muted);cursor:pointer}nav button:hover{background:rgba(255,255,255,.07);color:var(--color-text)}.viewer{height:calc(100% - 42px);position:relative}.resize{position:absolute;z-index:5}.n,.s{left:8px;right:8px;height:6px;cursor:ns-resize}.n{top:0}.s{bottom:0}.e,.w{top:8px;bottom:8px;width:6px;cursor:ew-resize}.e{right:0}.w{left:0}.ne,.nw,.se,.sw{width:10px;height:10px}.ne{right:0;top:0;cursor:nesw-resize}.nw{left:0;top:0;cursor:nwse-resize}.se{right:0;bottom:0;cursor:nwse-resize}.sw{left:0;bottom:0;cursor:nesw-resize}.dock{position:fixed;right:18px;bottom:18px;z-index:8000;height:38px;padding:0 14px;border:1px solid var(--color-border);border-radius:7px;background:#0c0f16;color:var(--color-muted);cursor:pointer}.dock span{margin-right:8px;color:var(--color-primary)}
@media(max-width:760px){.window{min-width:0;min-height:0}.resize{display:none}.titlebar{cursor:default}}
</style>
