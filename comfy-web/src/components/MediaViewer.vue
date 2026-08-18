<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  ArrowLeft,
  ArrowRight,
  Camera,
  Close,
  Download,
  RefreshLeft,
  VideoPause,
  VideoPlay,
} from '@element-plus/icons-vue'

type MediaType = 'image' | 'video'

const props = defineProps<{
  visible: boolean
  src: string
  type?: MediaType
  assetId?: number
  showNav?: boolean
  indexText?: string
  submitter?: string | null
  approvedAt?: string | null
}>()

const emit = defineEmits<{
  close: []
  prev: []
  next: []
}>()

const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'avif']
const mediaType = computed<MediaType>(() => {
  if (props.type) return props.type
  const extension = props.src.split('?')[0].split('.').pop()?.toLowerCase() || ''
  return imageExtensions.includes(extension) ? 'image' : 'video'
})
const fileName = computed(() => {
  const cleanSrc = props.src.split('?')[0].replace(/\\/g, '/')
  return decodeURIComponent(cleanSrc.split('/').pop() || '未命名素材')
})
const hasProjectInfo = computed(() => Boolean(props.submitter || props.approvedAt))

const stageRef = ref<HTMLElement | null>(null)
const videoRef = ref<HTMLVideoElement | null>(null)
const mediaWidth = ref(0)
const mediaHeight = ref(0)
const fileSize = ref<number | null>(null)
const scale = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const extracting = ref(false)
const extractingEnds = ref(false)
const notice = ref<{ type: 'success' | 'error' | 'warning'; message: string } | null>(null)
let noticeTimer: ReturnType<typeof setTimeout> | null = null
let fileSizeRequestId = 0

const dimensionsText = computed(() => (
  mediaWidth.value && mediaHeight.value ? `${mediaWidth.value} × ${mediaHeight.value}` : '读取中'
))

watch(() => [props.visible, props.src, mediaType.value] as const, ([visible]) => {
  if (!visible) {
    videoRef.value?.pause()
    return
  }
  resetMediaState()
  loadFileSize()
}, { immediate: true })

function resetMediaState() {
  scale.value = 1
  offsetX.value = 0
  offsetY.value = 0
  mediaWidth.value = 0
  mediaHeight.value = 0
  fileSize.value = null
  isPlaying.value = false
  currentTime.value = 0
  duration.value = 0
  stopDrag()
  if (videoRef.value) {
    videoRef.value.pause()
    videoRef.value.currentTime = 0
    videoRef.value.load()
  }
}

async function loadFileSize() {
  if (!props.src) return
  const requestId = ++fileSizeRequestId
  try {
    const response = await fetch(props.src, { method: 'HEAD' })
    const size = Number(response.headers.get('content-length'))
    if (requestId === fileSizeRequestId && response.ok && Number.isFinite(size) && size > 0) {
      fileSize.value = size
    }
  } catch {
    // 文件大小是辅助信息，读取失败不影响预览。
  }
}

function formatFileSize(bytes: number | null) {
  if (!bytes) return '未知'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds)) return '0:00'
  const minutes = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${minutes}:${String(secs).padStart(2, '0')}`
}

function onImageLoad(event: Event) {
  const image = event.currentTarget as HTMLImageElement
  mediaWidth.value = image.naturalWidth
  mediaHeight.value = image.naturalHeight
}

function onLoadedMetadata() {
  const video = videoRef.value
  if (!video) return
  duration.value = video.duration || 0
  mediaWidth.value = video.videoWidth
  mediaHeight.value = video.videoHeight
}

function changeScale(delta: number, pointerX = 0, pointerY = 0) {
  if (mediaType.value !== 'image') return
  const previousScale = scale.value
  const nextScale = Math.max(0.5, Math.min(5, previousScale + delta))
  if (nextScale === previousScale) return
  if (nextScale <= 1) {
    offsetX.value = 0
    offsetY.value = 0
  } else {
    const ratio = nextScale / previousScale
    offsetX.value = pointerX - (pointerX - offsetX.value) * ratio
    offsetY.value = pointerY - (pointerY - offsetY.value) * ratio
  }
  scale.value = nextScale
}

function handleWheel(event: WheelEvent) {
  if (mediaType.value !== 'image') return
  event.preventDefault()
  const rect = stageRef.value?.getBoundingClientRect()
  const pointerX = rect ? event.clientX - (rect.left + rect.width / 2) : 0
  const pointerY = rect ? event.clientY - (rect.top + rect.height / 2) : 0
  changeScale(event.deltaY > 0 ? -0.1 : 0.1, pointerX, pointerY)
}

function resetView() {
  scale.value = 1
  offsetX.value = 0
  offsetY.value = 0
}

function startDrag(event: PointerEvent) {
  if (mediaType.value !== 'image' || scale.value <= 1) return
  isDragging.value = true
  dragStartX.value = event.clientX - offsetX.value
  dragStartY.value = event.clientY - offsetY.value
  window.addEventListener('pointermove', drag)
  window.addEventListener('pointerup', stopDrag)
}

function drag(event: PointerEvent) {
  if (!isDragging.value) return
  offsetX.value = event.clientX - dragStartX.value
  offsetY.value = event.clientY - dragStartY.value
}

function stopDrag() {
  if (!isDragging.value) return
  isDragging.value = false
  window.removeEventListener('pointermove', drag)
  window.removeEventListener('pointerup', stopDrag)
}

function togglePlay() {
  const video = videoRef.value
  if (!video) return
  isPlaying.value ? video.pause() : video.play()
}

function onTimeUpdate() {
  currentTime.value = videoRef.value?.currentTime || 0
}

function seek(event: MouseEvent) {
  if (!videoRef.value || !duration.value) return
  const bar = event.currentTarget as HTMLElement
  const rect = bar.getBoundingClientRect()
  videoRef.value.currentTime = ((event.clientX - rect.left) / rect.width) * duration.value
}

function showNotice(type: 'success' | 'error' | 'warning', message: string) {
  notice.value = { type, message }
  if (noticeTimer) clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => {
    notice.value = null
    noticeTimer = null
  }, 3000)
}

async function doExtract(timeSec: number) {
  if (!props.assetId) throw new Error('无法获取资产ID')
  const userText = localStorage.getItem('user')
  if (!userText) throw new Error('请先登录')
  const user = JSON.parse(userText)
  const response = await fetch('/api/api-proxy/extract-frame', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ asset_id: props.assetId, time_sec: timeSec, user_id: user.id }),
  })
  if (!response.ok) throw new Error('抽帧失败')
}

async function extractFrame() {
  videoRef.value?.pause()
  extracting.value = true
  try {
    await doExtract(currentTime.value)
    showNotice('success', '抽帧成功，已保存到资产库')
  } catch (error: any) {
    showNotice('error', error.message || '抽帧失败')
  } finally {
    extracting.value = false
  }
}

async function extractEnds() {
  if (!duration.value) {
    showNotice('warning', '视频时长未加载')
    return
  }
  videoRef.value?.pause()
  extractingEnds.value = true
  try {
    await doExtract(0)
    await doExtract(Math.max(0, duration.value - 0.1))
    showNotice('success', '首尾帧已保存到资产库')
  } catch (error: any) {
    showNotice('error', error.message || '抽帧失败')
  } finally {
    extractingEnds.value = false
  }
}

function download() {
  const anchor = document.createElement('a')
  anchor.href = props.src
  anchor.download = fileName.value
  anchor.click()
}

function close() {
  videoRef.value?.pause()
  emit('close')
}

function handleKeydown(event: KeyboardEvent) {
  if (!props.visible) return
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
  } else if (props.showNav && event.key === 'ArrowLeft') {
    event.preventDefault()
    emit('prev')
  } else if (props.showNav && event.key === 'ArrowRight') {
    event.preventDefault()
    emit('next')
  } else if (mediaType.value === 'video' && event.code === 'Space') {
    event.preventDefault()
    togglePlay()
  }
}

onMounted(() => window.addEventListener('keydown', handleKeydown))
onUnmounted(() => {
  stopDrag()
  window.removeEventListener('keydown', handleKeydown)
  if (noticeTimer) clearTimeout(noticeTimer)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="media-viewer">
      <div v-if="visible" class="media-viewer-overlay" @click.self="close">
        <Transition name="media-notice">
          <div v-if="notice" class="media-notice" :class="notice.type" role="status">
            <span class="media-notice-dot" />
            {{ notice.message }}
          </div>
        </Transition>

        <section class="media-viewer-dialog" role="dialog" aria-modal="true" :aria-label="fileName">
          <div class="media-main">
            <div
              ref="stageRef"
              class="media-stage"
              :class="{ draggable: mediaType === 'image' && scale > 1, dragging: isDragging }"
              @wheel="handleWheel"
            >
              <img
                v-if="mediaType === 'image'"
                :src="src"
                class="media-image"
                :style="{ transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})` }"
                draggable="false"
                @load="onImageLoad"
                @pointerdown.prevent="startDrag"
              />
              <video
                v-else
                ref="videoRef"
                :src="src"
                class="media-video"
                @play="isPlaying = true"
                @pause="isPlaying = false"
                @timeupdate="onTimeUpdate"
                @loadedmetadata="onLoadedMetadata"
                @click="togglePlay"
              />

              <button
                v-if="showNav"
                class="media-nav media-nav-prev"
                type="button"
                title="上一个"
                aria-label="上一个"
                @click="emit('prev')"
              >
                <el-icon><ArrowLeft /></el-icon>
              </button>
              <button
                v-if="showNav"
                class="media-nav media-nav-next"
                type="button"
                title="下一个"
                aria-label="下一个"
                @click="emit('next')"
              >
                <el-icon><ArrowRight /></el-icon>
              </button>
              <span v-if="indexText" class="media-index">{{ indexText }}</span>
            </div>

            <footer class="media-toolbar">
              <template v-if="mediaType === 'image'">
                <button class="media-icon-button" type="button" title="缩小" aria-label="缩小" @click="changeScale(-0.1)">−</button>
                <span class="media-scale">{{ Math.round(scale * 100) }}%</span>
                <button class="media-icon-button" type="button" title="放大" aria-label="放大" @click="changeScale(0.1)">＋</button>
                <button class="media-tool-button" type="button" @click="resetView">
                  <el-icon><RefreshLeft /></el-icon>
                  适应窗口
                </button>
              </template>
              <template v-else>
                <button class="media-icon-button media-play" type="button" :title="isPlaying ? '暂停' : '播放'" @click="togglePlay">
                  <el-icon><VideoPause v-if="isPlaying" /><VideoPlay v-else /></el-icon>
                </button>
                <span class="media-time">{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span>
                <div class="media-progress" @click="seek">
                  <div class="media-progress-fill" :style="{ width: duration ? `${currentTime / duration * 100}%` : '0%' }" />
                </div>
                <button class="media-tool-button" type="button" :disabled="extracting" @click="extractFrame">
                  <el-icon><Camera /></el-icon>
                  {{ extracting ? '抽帧中' : '抽帧' }}
                </button>
                <button class="media-tool-button" type="button" :disabled="extractingEnds" @click="extractEnds">
                  {{ extractingEnds ? '处理中' : '抽取首尾帧' }}
                </button>
              </template>
            </footer>
          </div>

          <aside class="media-details">
            <header class="media-details-header">
              <span>素材信息</span>
              <button class="media-icon-button media-close" type="button" title="关闭" aria-label="关闭" @click="close">
                <el-icon><Close /></el-icon>
              </button>
            </header>

            <div class="media-details-body">
              <span class="media-type-label">{{ mediaType === 'image' ? '图片' : '视频' }}</span>
              <strong class="media-file-name" :title="fileName">{{ fileName }}</strong>

              <dl class="media-facts">
                <div>
                  <dt>尺寸</dt>
                  <dd>{{ dimensionsText }}</dd>
                </div>
                <div>
                  <dt>大小</dt>
                  <dd>{{ formatFileSize(fileSize) }}</dd>
                </div>
                <div v-if="mediaType === 'video' && duration">
                  <dt>时长</dt>
                  <dd>{{ formatTime(duration) }}</dd>
                </div>
              </dl>

              <section v-if="hasProjectInfo" class="media-project-info">
                <h3>项目记录</h3>
                <dl class="media-facts">
                  <div v-if="submitter">
                    <dt>提交人</dt>
                    <dd>{{ submitter }}</dd>
                  </div>
                  <div v-if="approvedAt">
                    <dt>通过时间</dt>
                    <dd>{{ approvedAt }}</dd>
                  </div>
                </dl>
              </section>
            </div>

            <footer class="media-details-footer">
              <button class="media-download-button" type="button" @click="download">
                <el-icon><Download /></el-icon>
                下载素材
              </button>
            </footer>
          </aside>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.media-viewer-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(3, 5, 8, 0.88);
  backdrop-filter: blur(10px);
}

.media-viewer-dialog {
  width: min(94vw, 1440px);
  height: min(90vh, 900px);
  min-height: 440px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: #111318;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.62);
  color: #f4f5f7;
}

.media-main {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
}

.media-type-label {
  display: inline-flex;
  width: fit-content;
  padding: 3px 7px;
  border: 1px solid rgba(112, 181, 255, 0.4);
  border-radius: 4px;
  color: #9bcbff;
  font-size: 11px;
  line-height: 1.4;
}

.media-file-name {
  display: block;
  margin-top: 12px;
  color: rgba(255, 255, 255, 0.94);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.media-facts {
  margin: 24px 0 0;
}

.media-facts > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 42px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.media-facts dt {
  color: rgba(255, 255, 255, 0.42);
  font-size: 11px;
  font-weight: 500;
}

.media-facts dd {
  margin: 0;
  color: rgba(255, 255, 255, 0.84);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.media-details {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  border-left: 1px solid rgba(255, 255, 255, 0.09);
  background: #191c22;
}

.media-details-header {
  min-height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px 10px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.09);
}

.media-details-header > span {
  color: rgba(255, 255, 255, 0.68);
  font-size: 12px;
  font-weight: 600;
}

.media-details-body {
  min-height: 0;
  overflow-y: auto;
  padding: 22px 20px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.18) transparent;
}

.media-project-info {
  margin-top: 30px;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.media-project-info h3 {
  margin: 0;
  color: rgba(255, 255, 255, 0.5);
  font-size: 11px;
  font-weight: 600;
}

.media-project-info .media-facts {
  margin-top: 8px;
}

.media-details-footer {
  padding: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.09);
}

.media-download-button {
  width: 100%;
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.9);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.16s, border-color 0.16s, color 0.16s;
}

.media-icon-button,
.media-tool-button,
.media-nav,
.media-download-button {
  border: 1px solid rgba(255, 255, 255, 0.14);
  color: rgba(255, 255, 255, 0.86);
  cursor: pointer;
  transition: background 0.16s, border-color 0.16s, color 0.16s;
}

.media-icon-button:hover,
.media-tool-button:hover:not(:disabled),
.media-nav:hover,
.media-download-button:hover {
  border-color: rgba(255, 255, 255, 0.3);
  background: rgba(255, 255, 255, 0.13);
  color: #fff;
}

.media-icon-button:focus-visible,
.media-tool-button:focus-visible,
.media-nav:focus-visible,
.media-download-button:focus-visible {
  outline: 2px solid #70b5ff;
  outline-offset: 2px;
}

.media-icon-button {
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.06);
  font-size: 17px;
}

.media-close {
  width: 32px;
  height: 32px;
  flex-basis: 32px;
  border-radius: 50%;
  font-size: 16px;
}

.media-close:hover {
  transform: rotate(90deg);
}

.media-stage {
  position: relative;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background-color: #090b0e;
  background-image:
    linear-gradient(45deg, rgba(255,255,255,0.025) 25%, transparent 25%),
    linear-gradient(-45deg, rgba(255,255,255,0.025) 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, rgba(255,255,255,0.025) 75%),
    linear-gradient(-45deg, transparent 75%, rgba(255,255,255,0.025) 75%);
  background-position: 0 0, 0 8px, 8px -8px, -8px 0;
  background-size: 16px 16px;
  user-select: none;
}

.media-stage.draggable { cursor: grab; }
.media-stage.dragging { cursor: grabbing; }

.media-image,
.media-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.media-image {
  max-width: 100%;
  max-height: 100%;
  transition: transform 0.08s ease-out;
  transform-origin: center;
  touch-action: none;
}

.media-video {
  cursor: pointer;
  background: #050607;
}

.media-nav {
  position: absolute;
  top: 50%;
  z-index: 2;
  width: 40px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  background: rgba(9, 11, 14, 0.72);
  font-size: 20px;
  transform: translateY(-50%);
  backdrop-filter: blur(8px);
}

.media-nav-prev { left: 16px; }
.media-nav-next { right: 16px; }

.media-index {
  position: absolute;
  right: 16px;
  bottom: 14px;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(9, 11, 14, 0.72);
  color: rgba(255, 255, 255, 0.72);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  pointer-events: none;
}

.media-toolbar {
  min-height: 52px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.09);
  background: #191c22;
}

.media-tool-button {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.06);
  font-size: 12px;
  white-space: nowrap;
}

.media-tool-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.media-scale,
.media-time {
  color: rgba(255, 255, 255, 0.62);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.media-scale {
  width: 46px;
  text-align: center;
}

.media-play { font-size: 15px; }

.media-progress {
  position: relative;
  width: auto;
  min-width: 120px;
  max-width: 420px;
  flex: 1;
  height: 18px;
  display: flex;
  align-items: center;
  cursor: pointer;
}

.media-progress::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  height: 4px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.12);
}

.media-progress-fill {
  position: relative;
  z-index: 1;
  height: 4px;
  border-radius: 2px;
  background: #70b5ff;
}

.media-notice {
  position: fixed;
  top: 28px;
  left: 50%;
  z-index: 2;
  max-width: calc(100vw - 32px);
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 16px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 6px;
  background: #24272e;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5);
  color: rgba(255, 255, 255, 0.92);
  font-size: 13px;
  transform: translateX(-50%);
}

.media-notice-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.72);
}

.media-notice.success .media-notice-dot { background: #4ade80; }
.media-notice.error .media-notice-dot { background: #fb7185; }
.media-notice.warning .media-notice-dot { background: #facc15; }

.media-viewer-enter-active,
.media-viewer-leave-active,
.media-notice-enter-active,
.media-notice-leave-active {
  transition: opacity 0.18s ease;
}

.media-viewer-enter-active .media-viewer-dialog,
.media-viewer-leave-active .media-viewer-dialog {
  transition: transform 0.18s ease, opacity 0.18s ease;
}

.media-viewer-enter-from,
.media-viewer-leave-to,
.media-notice-enter-from,
.media-notice-leave-to {
  opacity: 0;
}

.media-viewer-enter-from .media-viewer-dialog,
.media-viewer-leave-to .media-viewer-dialog {
  opacity: 0;
  transform: translateY(8px) scale(0.985);
}

@media (max-width: 1100px) {
  .media-viewer-dialog {
    grid-template-columns: minmax(0, 1fr) 280px;
  }
}

@media (max-width: 760px) {
  .media-viewer-overlay { padding: 8px; }
  .media-viewer-dialog {
    width: calc(100vw - 16px);
    height: calc(100vh - 16px);
    min-height: 0;
    grid-template-columns: 1fr;
    grid-template-rows: minmax(0, 1fr) minmax(220px, 40vh);
  }
  .media-details {
    border-top: 1px solid rgba(255, 255, 255, 0.09);
    border-left: 0;
  }
  .media-details-header {
    min-height: 44px;
    padding: 6px 10px 6px 14px;
  }
  .media-details-body {
    padding: 10px 14px;
  }
  .media-file-name {
    margin-top: 7px;
    font-size: 13px;
    line-height: 1.4;
  }
  .media-facts {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0 16px;
    margin-top: 10px;
  }
  .media-facts > div {
    min-height: 30px;
  }
  .media-project-info {
    margin-top: 10px;
    padding-top: 8px;
  }
  .media-project-info .media-facts {
    grid-template-columns: 1fr;
    margin-top: 4px;
  }
  .media-details-footer {
    padding: 8px 10px;
  }
  .media-download-button {
    min-height: 32px;
  }
  .media-toolbar {
    overflow-x: auto;
    scrollbar-width: none;
  }
  .media-toolbar::-webkit-scrollbar { display: none; }
  .media-progress {
    min-width: 140px;
    flex: 0 0 140px;
  }
  .media-nav-prev { left: 8px; }
  .media-nav-next { right: 8px; }
}

@media (prefers-reduced-motion: reduce) {
  .media-viewer-enter-active,
  .media-viewer-leave-active,
  .media-viewer-enter-active .media-viewer-dialog,
  .media-viewer-leave-active .media-viewer-dialog,
  .media-notice-enter-active,
  .media-notice-leave-active,
  .media-image {
    transition: none;
  }
}
</style>
