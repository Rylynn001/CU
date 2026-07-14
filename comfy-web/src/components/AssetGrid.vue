<script setup lang="ts">
import FavoriteHeart from './FavoriteHeart.vue'
import ProjectManager from './ProjectManager.vue'
import { ref } from 'vue'

interface Asset {
  id: number
  location: string
  name?: string
  asset_type?: string
  tag?: number
}

defineProps<{
  assets: Asset[]
  loading: boolean
}>()

const emit = defineEmits<{
  preview: [asset: Asset]
  openVideo: [asset: Asset]
  download: [asset: Asset]
  setFavorite: [asset: Asset, tag: 0 | 1 | 2 | 3 | 4]
}>()

const showProjectManager = ref(false)
const currentAssetId = ref<number | undefined>(undefined)

function openAddToProjectDialog(asset: Asset) {
  currentAssetId.value = asset.id
  showProjectManager.value = true
}

function handleProjectManagerClose() {
  showProjectManager.value = false
  currentAssetId.value = undefined
}

function getMediaUrl(location: string) {
  if (/^https?:\/\//.test(location)) return location
  return `/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
}

function isVideo(asset: Asset): boolean {
  const ext = asset.location.split('.').pop()?.toLowerCase()
  return ['mp4', 'mov', 'avi', 'webm'].includes(ext || '')
}
</script>

<template>
  <div v-if="loading" class="loading">
    <div class="breath-ring">
      <div class="ring r1" /><div class="ring r2" /><div class="ring r3" />
      <div class="center-dot" />
    </div>
    <p class="loading-text">加载中...</p>
  </div>

  <div v-else-if="assets.length === 0" class="empty">
    <div class="empty-orb" />
    <p class="empty-text">暂无资产</p>
  </div>

  <div v-else class="gallery">
    <div v-for="asset in assets" :key="asset.id" class="gallery-item">
      <div
        v-if="isVideo(asset)"
        class="gallery-media video-thumb"
        @click="emit('openVideo', asset)"
      >
        <video :src="getMediaUrl(asset.location)" class="gallery-media" preload="metadata" />
        <div class="video-play-icon">▶</div>
      </div>
      <img
        v-else
        :src="getMediaUrl(asset.location)"
        class="gallery-media"
        @click="emit('preview', asset)"
      />
      <div class="gallery-info">
        <span class="gallery-name">{{ asset.name || asset.location.split(/[/\\]/).pop() }}</span>
        <span v-if="isVideo(asset)" class="gallery-type">视频</span>
      </div>
      <button class="download-btn" @click.stop="emit('download', asset)" title="下载">
        <span>⬇</span>
      </button>
      <div class="action-buttons">
        <button class="action-btn folder-btn" @click.stop="openAddToProjectDialog(asset)" title="添加到项目">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
        </button>
        <span class="fav-slot">
          <FavoriteHeart :tag="asset.tag || 0" @change="(t) => emit('setFavorite', asset, t)" />
        </span>
      </div>
    </div>
  </div>

  <!-- 项目管理器 -->
  <ProjectManager
    :visible="showProjectManager"
    :asset-id="currentAssetId"
    mode="add"
    @close="handleProjectManagerClose"
  />
</template>

<style scoped>
.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  padding: 80px 0;
}
.loading-text {
  font-size: 13px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 2px;
}
.breath-ring {
  position: relative;
  width: 100px; height: 100px;
  display: flex; align-items: center; justify-content: center;
}
.ring {
  position: absolute;
  border-radius: 50%;
  border: 1.5px solid rgba(108,99,255,0.5);
  animation: breathe 3s ease-in-out infinite;
}
.r1 { width: 100%; height: 100%; animation-delay: 0s; }
.r2 { width: 72%; height: 72%; animation-delay: 0.5s; border-color: rgba(167,139,250,0.5); }
.r3 { width: 44%; height: 44%; animation-delay: 1s; border-color: rgba(196,181,253,0.6); }
.center-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: #a78bfa;
  animation: pulse-dot 2s ease-in-out infinite;
}
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 80px 0;
}
.empty-orb {
  width: 60px; height: 60px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(108,99,255,0.15) 0%, transparent 70%);
  border: 1px solid rgba(108,99,255,0.15);
  animation: breathe 4s ease-in-out infinite;
}
.empty-text {
  font-size: 12px;
  color: rgba(255,255,255,0.2);
  letter-spacing: 2px;
}
.gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
}
.gallery-item {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08);
  transition: transform 0.2s, border-color 0.2s;
}
.gallery-item:hover {
  transform: translateY(-4px);
  border-color: rgba(108,99,255,0.3);
}
.gallery-media {
  width: 100%;
  height: 260px;
  object-fit: cover;
  display: block;
  cursor: pointer;
}
.video-thumb {
  position: relative;
  height: 260px;
  background: #000;
  cursor: pointer;
}
.video-thumb video {
  height: 260px;
}
.video-play-icon {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  color: rgba(255,255,255,0.8);
  background: rgba(0,0,0,0.25);
  transition: background 0.2s;
}
.video-thumb:hover .video-play-icon {
  background: rgba(0,0,0,0.4);
}
.gallery-info {
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.gallery-name {
  font-size: 12px;
  color: rgba(255,255,255,0.4);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 85%;
}
.gallery-type {
  font-size: 11px;
  color: rgba(167,139,250,0.6);
  background: rgba(167,139,250,0.1);
  padding: 2px 7px;
  border-radius: 10px;
}
.download-btn {
  position: absolute;
  bottom: 44px;
  right: 10px;
  width: 30px; height: 30px;
  border-radius: 50%;
  background: rgba(0,0,0,0.5);
  border: none;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  opacity: 0;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
}
.gallery-item:hover .download-btn { opacity: 1; }
.download-btn:hover { background: rgba(108,99,255,0.9); transform: scale(1.1); }

.action-buttons {
  position: absolute;
  top: 10px;
  right: 10px;
  display: flex;
  gap: 6px;
  align-items: center;
  opacity: 0;
  transition: opacity 0.2s;
  z-index: 2;
}

.gallery-item:hover .action-buttons { opacity: 1; }

.action-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(0,0,0,0.6);
  border: 1px solid rgba(255,255,255,0.2);
  color: rgba(255,255,255,0.85);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
}

.action-btn:hover {
  background: rgba(108,99,255,0.9);
  border-color: rgba(108,99,255,0.8);
  transform: scale(1.1);
}

.fav-slot {
  position: relative;
  top: 0;
  left: 0;
  opacity: 1;
  transition: opacity 0.2s;
  pointer-events: auto;
}

.action-buttons:has(.favorited) { opacity: 1; }

@keyframes breathe {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(0.95); }
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
