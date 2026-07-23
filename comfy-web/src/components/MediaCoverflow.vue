<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, onBeforeUpdate, nextTick } from 'vue'

export interface CoverflowItem {
  id: number
  url: string
  poster: string
  isVideo: boolean
  location?: string        // 拖拽时需要传递的完整资产路径
  isGenPlaceholder?: boolean  // 生成占位符
  genMode?: 'image' | 'video'
  isGenerating?: boolean
}

const props = defineProps<{
  items: CoverflowItem[]
  highlightIds?: number[]
  panelIndex?: number
  traceRootId?: number  // Fix1: 根节点卡片 id，在该卡片上显示"退出溯源"按钮
}>()

const emit = defineEmits<{
  remove: [id: number]
  open: [item: CoverflowItem]
  select: [item: CoverflowItem]
  'exit-trace': []  // Fix1
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const cardRefs = ref<HTMLDivElement[]>([])

function isHighlighted(id: number) {
  return props.highlightIds?.includes(id) ?? false
}

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

function jumpToIndex(index: number, count = props.items.length) {
  const safeIndex = Math.max(0, Math.min(index, count - 1))
  scroll.target = safeIndex * spacing.value
  scroll.current = scroll.target
  clampTarget()
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

// 每卡每帧的几何量（offset=相对容器中心的水平位移，scale），供锚点计算，避开旋转导致的包围盒偏移
const cardGeom: Array<{ offset: number; scale: number }> = []

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
    cardGeom[i] = { offset, scale }
  }
  raf = requestAnimationFrame(tick)
}

// 吸附到最近一张
function snap() {
  const idx = Math.round(scroll.target / spacing.value)
  scroll.target = idx * spacing.value
  clampTarget()
}

// 滚轮滚动
function onWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY || e.deltaX
  scroll.target += delta * 0.9
  clampTarget()
  window.clearTimeout(snapTimer)
  snapTimer = window.setTimeout(snap, 140)
}

// 单击 → 溯源（200ms 延迟，双击时取消）
let singleClickTimer = 0

function onCardClick(item: CoverflowItem) {
  window.clearTimeout(singleClickTimer)
  singleClickTimer = window.setTimeout(() => {
    emit('select', item)
  }, 200)
}

// 双击 → 预览（取消单击定时器避免重复触发）
function onCardDblClick(item: CoverflowItem) {
  window.clearTimeout(singleClickTimer)
  emit('open', item)
}

// 卡片拖拽开始 → 携带资产数据，支持跨面板移动
function onCardDragStart(e: DragEvent, item: CoverflowItem, i: number) {
  const data = JSON.stringify({
    id: item.id,
    location: item.location ?? item.url.split('/').pop() ?? String(item.id),
    asset_type: item.isVideo ? 'video' : 'picture',
    fromPanelIndex: props.panelIndex ?? -1,
  })
  e.dataTransfer?.setData('application/json', data)
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    // 浏览器默认用布局位置（transform前）计算ghost偏移，对有translateX的非居中卡片会漂移
    // 用getBoundingClientRect获取视觉位置（transform后）显式修正
    const card = cardRefs.value[i]
    if (card) {
      const rect = card.getBoundingClientRect()
      e.dataTransfer.setDragImage(card, e.clientX - rect.left, e.clientY - rect.top)
    }
  }
}

// 暴露卡片边缘锚点的页面坐标，供父组件画溯源连线
// 几何计算：卡片视觉中心 = 容器中心 + offset（rotateY/scale 均绕中心，不影响中心 x）；
// 上下边缘按 scale 后的卡片高度折算。避开 getBoundingClientRect 对旋转卡片返回的包围盒偏移。
function getCardAnchor(id: number, edge: 'top' | 'bottom' | 'center' = 'center'): { x: number; y: number } | null {
  const idx = props.items.findIndex((it) => it.id === id)
  if (idx < 0) return null
  const el = containerRef.value
  const geom = cardGeom[idx]
  if (!el || !geom) return null
  const box = el.getBoundingClientRect()
  const cx = box.left + box.width / 2 + geom.offset
  const cy = box.top + box.height / 2
  const halfH = (cardW.value / 0.72) * geom.scale / 2
  const y = edge === 'top' ? cy - halfH : edge === 'bottom' ? cy + halfH : cy
  return { x: cx, y }
}

defineExpose({ getCardAnchor })

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

onBeforeUpdate(() => {
  cardRefs.value = []
  cardGeom.length = 0
})

// items 变化后重算位置：追踪居中 item id，移除时找其新 index 精确 snap
watch(() => props.items, (newItems, oldItems) => {
  if (!oldItems || newItems.length >= oldItems.length) {
    // 卡片增加 → 滚到末尾（等 DOM 稳定）
    if (newItems.length > (oldItems?.length ?? 0)) {
      nextTick().then(() => {
        jumpToIndex(newItems.length - 1, newItems.length)
      })
    }
    return
  }
  // 卡片减少：找出原来居中的 item，在新列表里找它的新 index
  const centeredIdx = Math.max(0, Math.min(Math.round(scroll.current / spacing.value), oldItems.length - 1))
  const centeredId = oldItems[centeredIdx]?.id
  const newIdx = centeredId != null ? newItems.findIndex((it) => it.id === centeredId) : -1
  if (newIdx >= 0) {
    jumpToIndex(newIdx, newItems.length)
  } else {
    // 居中的那张被移走，吸附到最近合法位置
    jumpToIndex(Math.min(centeredIdx, newItems.length - 1), newItems.length)
  }
}, { deep: false })
</script>

<template>
  <div
    ref="containerRef"
    class="coverflow"
    @wheel="onWheel"
  >
    <div
      v-for="(item, i) in items"
      :key="item.id"
      :ref="(el) => { if (el) cardRefs[i] = el as HTMLDivElement }"
      class="cf-card"
      :class="{
        'cf-highlight': isHighlighted(item.id),
        'cf-placeholder': item.isGenPlaceholder,
        'cf-generating': item.isGenPlaceholder && item.isGenerating,
      }"
      :style="{ width: cardW + 'px', height: (cardW / 0.72) + 'px' }"
      :draggable="!item.isGenPlaceholder"
      @click.stop="onCardClick(item)"
      @dblclick.stop="!item.isGenPlaceholder && onCardDblClick(item)"
      @dragstart="!item.isGenPlaceholder && onCardDragStart($event, item, i)"
    >
      <!-- 普通媒体卡片 -->
      <template v-if="!item.isGenPlaceholder">
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
      </template>

      <!-- 生成占位符 -->
      <template v-else>
        <div class="cf-gen-inner">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
            <path v-if="item.genMode === 'video'" d="M15 10l4.553-2.069A1 1 0 0 1 21 8.82v6.36a1 1 0 0 1-1.447.89L15 14M3 8a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8z"/>
            <rect v-else x="3" y="3" width="18" height="18" rx="2"/>
            <line v-if="!item.genMode || item.genMode === 'image'" x1="12" y1="8" x2="12" y2="16"/>
            <line v-if="!item.genMode || item.genMode === 'image'" x1="8" y1="12" x2="16" y2="12"/>
          </svg>
          <span class="cf-gen-label">{{ item.isGenerating ? (item.genMode === 'video' ? '视频生成中' : '图片生成中') : (item.genMode === 'video' ? '视频生成' : '图片生成') }}</span>
          <span class="cf-gen-hint">{{ item.isGenerating ? '任务进行中' : '点击选择参考' }}</span>
        </div>
      </template>

      <!-- 连线锚点 -->
      <span class="cf-anchor cf-anchor-top" aria-hidden="true" />
      <span class="cf-anchor cf-anchor-bottom" aria-hidden="true" />

      <!-- Fix1: 退出溯源按钮，仅在根节点卡片上显示 -->
      <button
        v-if="item.id === traceRootId"
        type="button"
        class="cf-exit-trace"
        @click.stop="emit('exit-trace')"
        @pointerdown.stop
      >
        退出溯源
      </button>

      <!-- 移除按钮（普通卡片 + 占位符合并为一个） -->
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
  cursor: default;
  touch-action: pan-y;
}
.coverflow:active { cursor: default; }

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
  transition: box-shadow 0.2s, border-color 0.2s;
}

/* 溯源命中高亮 */
.cf-card.cf-highlight {
  border-color: rgba(166, 231, 226, 0.9);
  box-shadow: 0 0 0 2px rgba(166, 231, 226, 0.6), 0 12px 40px rgba(0, 0, 0, 0.4);
}

.cf-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  pointer-events: none;
  user-select: none;
}

/* 连线锚点：卡片水平中线上的 0 尺寸标记，随卡片一起 3D 变换 */
.cf-anchor {
  position: absolute;
  left: 50%;
  width: 0;
  height: 0;
  pointer-events: none;
}
.cf-anchor-top { top: 0; }
.cf-anchor-bottom { top: 100%; }

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

/* Fix1: 退出溯源按钮，覆盖在根节点卡片底部 */
.cf-exit-trace {
  position: absolute;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid rgba(166, 231, 226, 0.5);
  background: rgba(10, 14, 20, 0.88);
  color: #a6e7e2;
  font-size: 11px;
  cursor: pointer;
  backdrop-filter: blur(6px);
  white-space: nowrap;
  z-index: 3;
  transition: all 0.2s;
}
.cf-exit-trace:hover {
  background: rgba(166, 231, 226, 0.18);
  border-color: rgba(166, 231, 226, 0.8);
}
/* 占位符卡片 */
.cf-card.cf-placeholder {
  border-style: dashed;
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
}
.cf-card.cf-placeholder:hover {
  border-color: rgba(166, 231, 226, 0.5);
  background: rgba(166, 231, 226, 0.05);
}
.cf-card.cf-highlight.cf-placeholder {
  border-style: solid;
  border-color: rgba(255, 255, 255, 0.9);
  box-shadow:
    0 0 0 2px rgba(255, 255, 255, 0.45),
    0 0 18px 5px rgba(255, 255, 255, 0.22),
    0 0 48px 10px rgba(255, 255, 255, 0.1),
    0 12px 40px rgba(0, 0, 0, 0.4);
}
.cf-card.cf-highlight.cf-placeholder .cf-gen-inner {
  color: rgba(255, 255, 255, 0.7);
}
.cf-card.cf-placeholder.cf-generating {
  border-style: solid;
  border-color: rgba(166, 231, 226, 0.75);
  background: rgba(166, 231, 226, 0.1);
  box-shadow: 0 0 0 2px rgba(166, 231, 226, 0.18), 0 0 28px rgba(166, 231, 226, 0.2);
}
.cf-card.cf-placeholder.cf-generating .cf-gen-inner {
  color: rgba(166, 231, 226, 0.9);
  animation: cf-generating-pulse 1.6s ease-in-out infinite;
}
@keyframes cf-generating-pulse {
  0%, 100% { opacity: 0.65; }
  50% { opacity: 1; }
}
.cf-gen-inner {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: rgba(255, 255, 255, 0.35);
  pointer-events: none;
}
.cf-gen-label {
  font-size: 12px;
  letter-spacing: 0.5px;
}
.cf-gen-hint {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.2);
  letter-spacing: 0.5px;
}
</style>
