<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import AssetSidebar from '../components/AssetSidebar.vue'
import ImageViewer from '../components/ImageViewer.vue'
import VideoPlayer from '../components/VideoPlayer.vue'
import MediaCoverflow, { type CoverflowItem } from '../components/MediaCoverflow.vue'

interface Asset {
  id: number
  location: string
  asset_type?: string
  tag?: number
}

interface PanelState {
  ratio: number
  assets: Asset[]
}

const panels = ref<PanelState[]>([
  { ratio: 1, assets: [] },
  { ratio: 1, assets: [] },
  { ratio: 1, assets: [] },
])

const resizing = ref<{ index: number; startY: number; first: number; second: number } | null>(null)

// 拖拽视觉反馈：isDragging 控制页面变暗，dragOverIndex 标记当前悬停的面板
const isDragging = ref(false)
const dragOverIndex = ref<number | null>(null)
function handleGlobalDragStart() { isDragging.value = true }
function handleGlobalDragEnd() { isDragging.value = false; dragOverIndex.value = null }
onMounted(() => {
  window.addEventListener('dragstart', handleGlobalDragStart)
  window.addEventListener('dragend', handleGlobalDragEnd)
})
onUnmounted(() => {
  window.removeEventListener('dragstart', handleGlobalDragStart)
  window.removeEventListener('dragend', handleGlobalDragEnd)
})

const panelStyles = computed(() => panels.value.map((panel) => ({
  flexGrow: panel.ratio,
  flexBasis: 0,
})))

function getMediaUrl(location: string) {
  return `/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
}

function isVideo(asset: Asset) {
  const ext = asset.location.split('.').pop()?.toLowerCase()
  return ['mp4', 'mov', 'avi', 'webm'].includes(ext || '')
}

// 视频首帧：加 #t=0.1 让 <video> 显示首帧画面而非黑屏
function getPoster(asset: Asset) {
  return `${getMediaUrl(asset.location)}#t=0.1`
}

// 接收 AssetSidebar 的 select 事件（payload 为数组）或拖放的单个资产
function handleSidebarSelect(payload: Asset | Asset[]) {
  const list = Array.isArray(payload) ? payload : [payload]
  list.forEach((asset) => addAssetToPanel(asset))
}

function addAssetToPanel(asset: Asset, index?: number) {
  const targets = index === undefined ? panels.value : [panels.value[index]]
  targets.forEach((panel) => {
    if (!panel.assets.some((item) => item.id === asset.id)) {
      panel.assets.push(asset)
    }
  })
  ElMessage.success('已添加到节点面板')
}

// 拖拽资产到指定面板
function handlePanelDrop(e: DragEvent, index: number) {
  dragOverIndex.value = null
  const data = e.dataTransfer?.getData('application/json')
  if (!data) return
  try {
    const asset: Asset = JSON.parse(data)
    addAssetToPanel(asset, index)
  } catch {
    // 忽略非资产数据
  }
}

// dragenter/dragleave 会在子元素间切换时反复冒泡触发，仅在真正离开面板边界（relatedTarget 不在面板内）时才取消高亮
function handlePanelDragLeave(e: DragEvent, index: number) {
  const related = e.relatedTarget as Node | null
  if (!related || !(e.currentTarget as HTMLElement).contains(related)) {
    if (dragOverIndex.value === index) dragOverIndex.value = null
  }
}

// 面板资产 → coverflow 组件所需的数据结构
const coverflowItems = computed(() =>
  panels.value.map((panel) =>
    panel.assets.map<CoverflowItem>((asset) => ({
      id: asset.id,
      url: getMediaUrl(asset.location),
      poster: getPoster(asset),
      isVideo: isVideo(asset),
    }))
  )
)

function removeAssetById(id: number, index: number) {
  panels.value[index].assets = panels.value[index].assets.filter((item) => item.id !== id)
}

// 双击预览：图片放大 / 视频播放
const showImageViewer = ref(false)
const previewUrl = ref('')
const showVideoPlayer = ref(false)
const activeVideoUrl = ref('')
const activeVideoId = ref<number | undefined>(undefined)

function openPreview(item: CoverflowItem) {
  if (item.isVideo) {
    activeVideoUrl.value = item.url
    activeVideoId.value = item.id
    showVideoPlayer.value = true
  } else {
    previewUrl.value = item.url
    showImageViewer.value = true
  }
}

function startResize(index: number, event: PointerEvent) {
  const first = panels.value[index]
  const second = panels.value[index + 1]
  if (!first || !second) return

  resizing.value = {
    index,
    startY: event.clientY,
    first: first.ratio,
    second: second.ratio,
  }
  window.addEventListener('pointermove', handleResize)
  window.addEventListener('pointerup', stopResize)
}

function handleResize(event: PointerEvent) {
  if (!resizing.value) return
  const { index, startY, first, second } = resizing.value
  const delta = (event.clientY - startY) / 180
  const total = first + second
  const nextFirst = Math.min(Math.max(first + delta, 0.45), total - 0.45)
  panels.value[index].ratio = nextFirst
  panels.value[index + 1].ratio = total - nextFirst
}

function stopResize() {
  resizing.value = null
  window.removeEventListener('pointermove', handleResize)
  window.removeEventListener('pointerup', stopResize)
}
</script>

<template>
  <div class="node-panel-page" :class="{ dragging: isDragging }">
    <div class="node-orb node-orb-2" />

    <main class="panel-workspace">
      <section class="panel-shell" aria-label="节点预览面板">
        <div class="panel-stack">
          <template v-for="(panel, index) in panels" :key="index">
            <article
              class="preview-panel"
              :class="{ 'drag-over': dragOverIndex === index }"
              :style="panelStyles[index]"
              @dragover.prevent
              @dragenter.prevent="dragOverIndex = index"
              @dragleave.prevent="handlePanelDragLeave($event, index)"
              @drop.prevent="handlePanelDrop($event, index)"
            >
              <MediaCoverflow
                v-if="panel.assets.length > 0"
                :items="coverflowItems[index]"
                @remove="(id) => removeAssetById(id, index)"
                @open="openPreview"
              />
              <div v-else class="panel-empty">拖拽资产到此处</div>
            </article>

            <button
              v-if="index < panels.length - 1"
              :key="`resize-${index}`"
              type="button"
              class="resize-handle"
              aria-label="调整面板高度"
              @pointerdown.prevent="startResize(index, $event)"
            />
          </template>
        </div>
      </section>

      <AssetSidebar @select="handleSidebarSelect" />
    </main>

    <ImageViewer :visible="showImageViewer" :src="previewUrl" @close="showImageViewer = false" />
    <VideoPlayer :visible="showVideoPlayer" :src="activeVideoUrl" :asset-id="activeVideoId" @close="showVideoPlayer = false" />
  </div>
</template>

<style scoped>
.node-panel-page {
  position: relative;
  height: 100vh;
  overflow: hidden;
  background: transparent;
  animation: page-enter 0.45s ease both;
}

.node-panel-page.dragging::after {
  content: '';
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.18);
  pointer-events: none;
  z-index: 200;
}

.node-orb {
  position: fixed;
  z-index: 0;
  border-radius: 50%;
  filter: blur(80px);
  pointer-events: none;
}

.node-orb-2 {
  right: 60px;
  bottom: -100px;
  width: 440px;
  height: 440px;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.07) 0%, transparent 70%);
}

.panel-workspace {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 14px;
  height: 100%;
  min-height: 0;
  padding: 14px;
}

.panel-shell {
  position: relative;
  flex: 0 0 74%;
  min-width: 0;
  min-height: 0;
}

.panel-stack {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.preview-panel {
  position: relative;
  min-height: 150px;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: rgba(7, 9, 15, 0.24);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  box-shadow: var(--shadow-soft);
  transition: border-color 0.2s, background 0.2s;
}

.preview-panel.drag-over {
  border-color: rgba(166, 231, 226, 0.5);
  background: rgba(166, 231, 226, 0.08);
}

.panel-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.25);
  letter-spacing: 1px;
}

.resize-handle {
  position: relative;
  height: 10px;
  flex: 0 0 10px;
  border: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
  cursor: row-resize;
}

.resize-handle::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 44px;
  height: 2px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.22);
  transform: translate(-50%, -50%);
}

.resize-handle:hover,
.resize-handle:focus-visible {
  background: rgba(255, 255, 255, 0.1);
}
</style>
