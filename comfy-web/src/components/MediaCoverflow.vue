<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'

export interface CoverflowItem {
  id: number
  url: string
  poster: string
  isVideo: boolean
}

const props = defineProps<{
  items: CoverflowItem[]
}>()

const emit = defineEmits<{
  remove: [id: number]
  open: [item: CoverflowItem]
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const cardRefs = ref<HTMLDivElement[]>([])

// 尺寸随容器变化（面板拖动缩放时重算）
const size = ref({ w: 1, h: 1 })
const cardW = ref(200)
const spacing = ref(220)

// 滚动：target 为目标位置，current 缓动逼近 target，产生惯性顺滑感
const scroll = { current: 0, target: 0 }
let raf = 0
let snapTimer = 0

function computeSize() {
  const el = containerRef.value
  if (!el) return
  size.value = { w: el.clientWidth, h: el.clientHeight }
  const cardH = Math.max(size.value.h * 0.8, 80)
  cardW.value = Math.min(cardH * 0.72, size.value.w * 0.5)
  spacing.value = cardW.value * 1.08
  clampTarget()
}

function clampTarget() {
  const max = Math.max(0, (props.items.length - 1) * spacing.value)
  scroll.target = Math.min(Math.max(scroll.target, 0), max)
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

// 每帧更新每张卡片的位移/缩放/3D 倾斜：离中心越近越大越正
function tick() {
  scroll.current = lerp(scroll.current, scroll.target, 0.09)
  const cards = cardRefs.value
  for (let i = 0; i < cards.length; i++) {
    const card = cards[i]
    if (!card) continue
    const offset = i * spacing.value - scroll.current
    const norm = offset / spacing.value
    const clampedNorm = Math.max(-3, Math.min(3, norm))
    const scale = Math.max(0.6, 1 - Math.abs(clampedNorm) * 0.16)
    const rotateY = Math.max(-24, Math.min(24, -clampedNorm * 22))
    const opacity = Math.max(0.35, 1 - Math.abs(clampedNorm) * 0.28)
    card.style.transform =
      `translate(-50%, -50%) translateX(${offset}px) scale(${scale}) rotateY(${rotateY}deg)`
    card.style.opacity = String(opacity)
    card.style.zIndex = String(1000 - Math.round(Math.abs(offset)))
  }
  raf = requestAnimationFrame(tick)
}

// 吸附到最近一张
function snap() {
  const idx = Math.round(scroll.target / spacing.value)
  scroll.target = idx * spacing.value
  clampTarget()
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY || e.deltaX
  scroll.target += delta * 0.9
  clampTarget()
  window.clearTimeout(snapTimer)
  snapTimer = window.setTimeout(snap, 140)
}

// 横向拖拽滚动
let dragging = false
let dragStartX = 0
let dragStartTarget = 0

function onPointerDown(e: PointerEvent) {
  dragging = true
  dragStartX = e.clientX
  dragStartTarget = scroll.target
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}
function onPointerMove(e: PointerEvent) {
  if (!dragging) return
  scroll.target = dragStartTarget - (e.clientX - dragStartX)
  clampTarget()
}
function onPointerUp() {
  if (!dragging) return
  dragging = false
  snap()
}

let ro: ResizeObserver | null = null

onMounted(async () => {
  await nextTick()
  computeSize()
  ro = new ResizeObserver(computeSize)
  if (containerRef.value) ro.observe(containerRef.value)
  raf = requestAnimationFrame(tick)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  window.clearTimeout(snapTimer)
  ro?.disconnect()
})

// items 变化后重算边界，并把新加入的卡片滚到视野
watch(() => props.items.length, async (len, prev) => {
  await nextTick()
  clampTarget()
  if (len > prev) scroll.target = (len - 1) * spacing.value
  clampTarget()
})
</script>

<template>
  <div
    ref="containerRef"
    class="coverflow"
    @wheel="onWheel"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
  >
    <div
      v-for="(item, i) in items"
      :key="item.id"
      :ref="(el) => { if (el) cardRefs[i] = el as HTMLDivElement }"
      class="cf-card"
      :style="{ width: cardW + 'px', height: (cardW / 0.72) + 'px' }"
      @dblclick="emit('open', item)"
    >
      <video
        v-if="item.isVideo"
        :src="item.poster"
        class="cf-media"
        preload="metadata"
        muted
        playsinline
        draggable="false"
      />
      <img v-else :src="item.url" class="cf-media" loading="lazy" draggable="false" />
      <div v-if="item.isVideo" class="cf-play">▶</div>
      <button
        type="button"
        class="cf-remove"
        title="移除"
        @click.stop="emit('remove', item.id)"
        @pointerdown.stop
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.coverflow {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  perspective: 1200px;
  cursor: grab;
  touch-action: pan-y;
}
.coverflow:active { cursor: grabbing; }

.cf-card {
  position: absolute;
  left: 50%;
  top: 50%;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--color-border);
  background: rgba(255, 255, 255, 0.04);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
  will-change: transform, opacity;
  cursor: pointer;
}

.cf-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  pointer-events: none;
  user-select: none;
}

.cf-play {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: rgba(255, 255, 255, 0.9);
  background: rgba(0, 0, 0, 0.26);
  pointer-events: none;
}

.cf-remove {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s, background 0.2s, transform 0.2s;
  backdrop-filter: blur(4px);
  z-index: 2;
}
.cf-card:hover .cf-remove { opacity: 1; }
.cf-remove:hover {
  background: rgba(244, 63, 94, 0.9);
  border-color: rgba(244, 63, 94, 0.8);
  transform: scale(1.12);
}
</style>
