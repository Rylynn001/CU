<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  visible: boolean
  src: string
  assetId?: number
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const videoRef = ref<HTMLVideoElement | null>(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const extracting = ref(false)

watch(() => props.visible, (v) => {
  if (!v) videoRef.value?.pause()
})

function onKeydown(e: KeyboardEvent) {
  if (!props.visible) return
  if (e.code === 'Space') {
    e.preventDefault()
    togglePlay()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

function close() {
  videoRef.value?.pause()
  emit('close')
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
    ElMessage.warning('无法获取资产ID')
    return
  }
  const userStr = localStorage.getItem('user')
  if (!userStr) { ElMessage.error('请先登录'); return }
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
    ElMessage.success('抽帧成功，已保存到资产库')
  } catch (e: any) {
    ElMessage.error(e.message || '抽帧失败')
  } finally {
    extracting.value = false
  }
}

async function extractEnds() {
  if (!duration.value) { ElMessage.warning('视频时长未加载'); return }
  videoRef.value?.pause()
  extractingEnds.value = true
  try {
    await doExtract(0)
    await doExtract(Math.max(0, duration.value - 0.1))
    ElMessage.success('首尾帧已保存到资产库')
  } catch (e: any) {
    ElMessage.error(e.message || '抽帧失败')
  } finally {
    extractingEnds.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="vp-overlay" @click.self="close">
      <div class="vp-modal">
        <button class="vp-close" @click="close">×</button>
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

.vp-modal {
  position: relative;
  width: min(90vw, 1000px);
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

.vp-video {
  width: 100%;
  max-height: 70vh;
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
  background: rgba(108, 99, 255, 0.9);
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
  background: rgba(108, 99, 255, 0.4);
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
  background: rgba(108, 99, 255, 0.15);
  border: 1px solid rgba(108, 99, 255, 0.35);
  color: rgba(167, 139, 250, 0.9);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.vp-extract-btn:hover:not(:disabled) {
  background: rgba(108, 99, 255, 0.35);
  border-color: rgba(108, 99, 255, 0.6);
  color: #fff;
}
.vp-extract-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
