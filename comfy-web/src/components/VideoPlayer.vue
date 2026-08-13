<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  visible: boolean
  src: string
  assetId?: number
  showNav?: boolean
}>()

const emit = defineEmits<{
  close: []
  prev: []
  next: []
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const extracting = ref(false)
const notice = ref<{ type: 'success' | 'error' | 'warning'; message: string } | null>(null)
let noticeTimer: ReturnType<typeof setTimeout> | null = null

function showNotice(type: 'success' | 'error' | 'warning', message: string) {
  notice.value = { type, message }
  if (noticeTimer) clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => {
    notice.value = null
    noticeTimer = null
  }, 3000)
}

watch(() => props.visible, (v) => {
  if (!v) videoRef.value?.pause()
})

// 监听视频源变化，重置播放器状态
watch(() => props.src, () => {
  if (videoRef.value) {
    videoRef.value.pause()
    videoRef.value.currentTime = 0
    isPlaying.value = false
    currentTime.value = 0
    duration.value = 0
    videoRef.value.load()
  }
})

function onKeydown(e: KeyboardEvent) {
  if (!props.visible) return
  if (e.code === 'Space') {
    e.preventDefault()
    togglePlay()
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault()
    emit('prev')
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    emit('next')
  } else if (e.key === 'Escape') {
    e.preventDefault()
    close()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  if (noticeTimer) clearTimeout(noticeTimer)
})

function close() {
  videoRef.value?.pause()
  emit('close')
}

function download() {
  const a = document.createElement('a')
  a.href = props.src
  a.download = props.src.replace(/\\/g, '/').split('/').pop()?.split('?')[0] || 'video.mp4'
  a.click()
}

function togglePlay() {
  if (!videoRef.value) return
  isPlaying.value ? videoRef.value.pause() : videoRef.value.play()
}

function onTimeUpdate() {
  currentTime.value = videoRef.value?.currentTime ?? 0
}

function onLoadedMetadata() {
  duration.value = videoRef.value?.duration ?? 0
}

function seek(e: MouseEvent) {
  if (!videoRef.value || !duration.value) return
  const bar = e.currentTarget as HTMLElement
  videoRef.value.currentTime = (e.offsetX / bar.clientWidth) * duration.value
}

function formatTime(sec: number) {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

const extractingEnds = ref(false)

async function doExtract(timeSec: number) {
  if (!props.assetId) {
    throw new Error('无法获取资产ID')
  }
  const userStr = localStorage.getItem('user')
  if (!userStr) throw new Error('请先登录')
  const user = JSON.parse(userStr)

  const res = await fetch('/api/api-proxy/extract-frame', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ asset_id: props.assetId, time_sec: timeSec, user_id: user.id }),
  })
  if (!res.ok) throw new Error('抽帧失败')
}

async function extractFrame() {
  videoRef.value?.pause()
  extracting.value = true
  try {
    await doExtract(currentTime.value)
    showNotice('success', '抽帧成功，已保存到资产库')
  } catch (e: any) {
    showNotice('error', e.message || '抽帧失败')
  } finally {
    extracting.value = false
  }
}

async function extractEnds() {
  if (!duration.value) { showNotice('warning', '视频时长未加载'); return }
  videoRef.value?.pause()
  extractingEnds.value = true
  try {
    await doExtract(0)
    await doExtract(Math.max(0, duration.value - 0.1))
    showNotice('success', '首尾帧已保存到资产库')
  } catch (e: any) {
    showNotice('error', e.message || '抽帧失败')
  } finally {
    extractingEnds.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="vp-overlay" @click.self="close">
      <Transition name="vp-notice">
        <div v-if="notice" class="vp-notice" :class="notice.type" role="status">
          <span class="vp-notice-dot" />
          {{ notice.message }}
        </div>
      </Transition>
      <div class="vp-modal">
        <button class="vp-close" @click="close">×</button>
        <button v-if="showNav" class="vp-nav vp-nav-prev" @click="emit('prev')" title="上一个 (←)">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
        <button v-if="showNav" class="vp-nav vp-nav-next" @click="emit('next')" title="下一个 (→)">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
        <video
          ref="videoRef"
          :src="src"
          class="vp-video"
          @play="isPlaying = true"
          @pause="isPlaying = false"
          @timeupdate="onTimeUpdate"
          @loadedmetadata="onLoadedMetadata"
          @click="togglePlay"
        />
        <div class="vp-toolbar">
          <div class="vp-progress" @click="seek">
            <div class="vp-fill" :style="{ width: duration ? (currentTime / duration * 100) + '%' : '0%' }" />
          </div>
          <div class="vp-controls">
            <button class="vp-play-btn" @click="togglePlay">
              <svg v-if="!isPlaying" width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5,3 19,12 5,21" />
              </svg>
              <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" />
              </svg>
            </button>
            <span class="vp-time">{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span>
            <div class="vp-spacer" />
            <button class="vp-extract-btn" :disabled="extracting" @click="extractFrame">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;flex-shrink:0">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <circle cx="12" cy="12" r="3"/>
                <line x1="12" y1="3" x2="12" y2="7"/>
                <line x1="12" y1="17" x2="12" y2="21"/>
                <line x1="3" y1="12" x2="7" y2="12"/>
                <line x1="17" y1="12" x2="21" y2="12"/>
              </svg>
              {{ extracting ? '抽帧中...' : '抽帧' }}
            </button>
            <button class="vp-extract-btn" :disabled="extractingEnds" @click="extractEnds">
              {{ extractingEnds ? '处理中...' : '抽取首尾帧' }}
            </button>
            <button class="vp-extract-btn" @click="download" title="下载">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px;flex-shrink:0">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              下载
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.vp-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.vp-notice {
  position: fixed;
  top: 28px;
  left: 50%;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 9px;
  max-width: calc(100vw - 32px);
  padding: 10px 16px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 8px;
  background: #202126;
  color: rgba(255, 255, 255, 0.92);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5);
  font-size: 13px;
  transform: translateX(-50%);
}

.vp-notice-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.72);
  flex-shrink: 0;
}
.vp-notice.success .vp-notice-dot { background: #4ade80; }
.vp-notice.error .vp-notice-dot { background: #fb7185; }
.vp-notice.warning .vp-notice-dot { background: #facc15; }

.vp-notice-enter-active,
.vp-notice-leave-active { transition: opacity 0.2s, transform 0.2s; }
.vp-notice-enter-from,
.vp-notice-leave-to { opacity: 0; transform: translate(-50%, -8px); }

.vp-modal {
  position: relative;
  width: min(90vw, 1400px);
  background: #000;
  border-radius: 12px;
  overflow: hidden;
}

.vp-close {
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 10;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: white;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}
.vp-close:hover {
  background: rgba(220, 50, 50, 0.7);
}

.vp-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 10;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.vp-nav:hover {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.4);
  transform: translateY(-50%) scale(1.1);
}
.vp-nav-prev {
  left: 20px;
}
.vp-nav-next {
  right: 20px;
}

.vp-video {
  width: 100%;
  height: 70vh;
  display: block;
  object-fit: contain;
  cursor: pointer;
}

.vp-toolbar {
  background: rgba(0, 0, 0, 0.9);
  padding: 8px 12px 10px;
}

.vp-progress {
  height: 4px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
  cursor: pointer;
  margin-bottom: 10px;
}

.vp-fill {
  height: 100%;
  background: rgba(255,255,255, 0.9);
  border-radius: 2px;
  transition: width 0.1s linear;
}

.vp-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.vp-play-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.2s;
}
.vp-play-btn:hover {
  background: rgba(255,255,255, 0.4);
}

.vp-time {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.vp-spacer { flex: 1; }

.vp-extract-btn {
  display: flex;
  align-items: center;
  padding: 5px 14px;
  border-radius: 6px;
  background: rgba(255,255,255, 0.15);
  border: 1px solid rgba(255,255,255, 0.35);
  color: rgba(255,255,255, 0.9);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.vp-extract-btn:hover:not(:disabled) {
  background: rgba(255,255,255, 0.35);
  border-color: rgba(255,255,255, 0.6);
  color: #fff;
}
.vp-extract-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
