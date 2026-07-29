<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  visible: boolean
  src: string
  showNav?: boolean
  indexText?: string
}>()

const emit = defineEmits<{
  close: []
  prev: []
  next: []
}>()

const scale = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)
const viewerContent = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const MIN_SCALE = 0.5
const MAX_SCALE = 5

watch(() => props.visible, (visible) => {
  if (visible) {
    resetView()
  }
})

watch(() => props.src, () => {
  resetView()
})

function resetView() {
  scale.value = 1
  offsetX.value = 0
  offsetY.value = 0
  stopDrag()
}

function handleWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  const previousScale = scale.value
  const nextScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, previousScale + delta))
  if (nextScale === previousScale) return

  if (nextScale <= 1) {
    offsetX.value = 0
    offsetY.value = 0
  } else {
    const rect = viewerContent.value?.getBoundingClientRect()
    if (rect) {
      const pointerX = e.clientX - (rect.left + rect.width / 2)
      const pointerY = e.clientY - (rect.top + rect.height / 2)
      const scaleRatio = nextScale / previousScale
      offsetX.value = pointerX - (pointerX - offsetX.value) * scaleRatio
      offsetY.value = pointerY - (pointerY - offsetY.value) * scaleRatio
    }
  }
  scale.value = nextScale
}

function startDrag(e: PointerEvent) {
  if (scale.value <= 1) return
  isDragging.value = true
  dragStartX.value = e.clientX - offsetX.value
  dragStartY.value = e.clientY - offsetY.value
  window.addEventListener('pointermove', drag)
  window.addEventListener('pointerup', stopDrag)
}

function drag(e: PointerEvent) {
  if (!isDragging.value) return
  offsetX.value = e.clientX - dragStartX.value
  offsetY.value = e.clientY - dragStartY.value
}

function stopDrag() {
  if (!isDragging.value) return
  isDragging.value = false
  window.removeEventListener('pointermove', drag)
  window.removeEventListener('pointerup', stopDrag)
}

function close() {
  emit('close')
}

function prev() {
  emit('prev')
}

function next() {
  emit('next')
}

function handleKeydown(e: KeyboardEvent) {
  if (!props.visible || e.key !== 'Escape') return
  e.preventDefault()
  close()
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  stopDrag()
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="img-viewer">
      <div v-if="visible" class="custom-image-viewer" @click="close" @wheel="handleWheel">
        <div ref="viewerContent" class="viewer-content" :class="{ draggable: scale > 1, dragging: isDragging }" @click.stop>
          <img
            :src="src"
            class="viewer-image"
            :style="{ transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})` }"
            draggable="false"
            @pointerdown.prevent="startDrag"
          />
          <button class="viewer-close" @click="close" title="关闭 (ESC)">✕</button>
          <button v-if="showNav" class="viewer-nav viewer-prev" @click="prev" title="上一张 (←)">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>
          <button v-if="showNav" class="viewer-nav viewer-next" @click="next" title="下一张 (→)">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </button>
          <div class="viewer-scale-info">{{ Math.round(scale * 100) }}%</div>
          <div v-if="indexText" class="viewer-index-info">{{ indexText }}</div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.custom-image-viewer {
  position: fixed;
  inset: 0;
  z-index: 2500;
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.viewer-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  cursor: default;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;
}
.viewer-content.draggable {
  cursor: grab;
}
.viewer-content.dragging {
  cursor: grabbing;
}
.viewer-image {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  display: block;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  transition: transform 0.1s ease-out;
  transform-origin: center center;
  touch-action: none;
}
.viewer-close {
  position: absolute;
  top: -40px;
  right: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(0, 0, 0, 0.4);
  color: rgba(255, 255, 255, 0.9);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.viewer-close:hover {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.4);
  transform: scale(1.1);
}
.viewer-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(0, 0, 0, 0.5);
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.viewer-nav:hover {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.4);
  transform: translateY(-50%) scale(1.1);
}
.viewer-prev {
  left: -60px;
}
.viewer-next {
  right: -60px;
}
.viewer-scale-info {
  position: absolute;
  bottom: -35px;
  left: 50%;
  transform: translateX(-50%);
  padding: 4px 12px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.8);
  font-size: 12px;
  pointer-events: none;
}
.viewer-index-info {
  position: absolute;
  bottom: -35px;
  right: 0;
  padding: 4px 12px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.8);
  font-size: 12px;
  pointer-events: none;
}

.img-viewer-enter-active,
.img-viewer-leave-active {
  transition: opacity 0.25s ease;
}
.img-viewer-enter-active .viewer-content,
.img-viewer-leave-active .viewer-content {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.img-viewer-enter-from,
.img-viewer-leave-to {
  opacity: 0;
}
.img-viewer-enter-from .viewer-content,
.img-viewer-leave-to .viewer-content {
  transform: scale(0.9);
  opacity: 0;
}
</style>
