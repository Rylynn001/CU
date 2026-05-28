<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElImageViewer } from 'element-plus'
import VideoPlayer from '../components/VideoPlayer.vue'
import { favoriteAsset } from '../api/apiService'

interface Asset {
  id: number
  location: string
  asset_type?: string
  tag?: number
}

const assets = ref<Asset[]>([])
const loading = ref(false)
const activeFilter = ref<'all' | 'picture' | 'video'>('all')
const favoritesOnly = ref(true)

// 图片预览
const showImageViewer = ref(false)
const previewImageUrl = ref('')
const previewInitialIndex = ref(0)

function previewImage(asset: Asset) {
  if (isVideo(asset)) return
  const index = assets.value.findIndex(a => a.id === asset.id)
  previewInitialIndex.value = index >= 0 ? index : 0
  previewImageUrl.value = getImageUrl(asset.location)
  showImageViewer.value = true
  document.documentElement.style.overflow = 'hidden'
}

function closeImageViewer() {
  showImageViewer.value = false
  document.documentElement.style.overflow = ''
}

// 视频播放器弹窗
const showVideoPlayer = ref(false)
const activeVideo = ref<Asset | null>(null)

function openVideo(asset: Asset) {
  activeVideo.value = asset
  showVideoPlayer.value = true
}

async function loadAssets(assetType?: 'picture' | 'video') {
  const userStr = localStorage.getItem('user')
  if (!userStr) {
    ElMessage.error('请先登录')
    return
  }

  const user = JSON.parse(userStr)
  loading.value = true

  try {
    let url = `/api/api-proxy/user/assets?user_id=${user.id}`
    if (assetType) url += `&asset_type=${assetType}`
    if (favoritesOnly.value) url += `&tag=1`
    const res = await fetch(url)
    if (!res.ok) {
      throw new Error('加载失败')
    }
    const data = await res.json()
    assets.value = data.assets || []
  } catch (e: any) {
    ElMessage.error(e.message || '加载资产失败')
  } finally {
    loading.value = false
  }
}

function setFilter(filter: 'all' | 'picture' | 'video') {
  activeFilter.value = filter
  loadAssets(filter === 'all' ? undefined : filter)
}

function setFavoritesOnly(val: boolean) {
  favoritesOnly.value = val
  loadAssets(activeFilter.value === 'all' ? undefined : activeFilter.value)
}

function getImageUrl(location: string) {
  return `/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
}

function getMediaUrl(location: string) {
  return `/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
}

function isVideo(asset: Asset): boolean {
  const ext = asset.location.split('.').pop()?.toLowerCase()
  return ['mp4', 'mov', 'avi', 'webm'].includes(ext || '')
}

function downloadImage(asset: Asset) {
  const url = isVideo(asset) ? getMediaUrl(asset.location) : getImageUrl(asset.location)
  const a = document.createElement('a')
  a.href = url
  a.download = asset.location.split(/[/\\]/).pop() || 'asset'
  a.click()
}

async function toggleFavorite(asset: Asset) {
  const userStr = localStorage.getItem('user')
  if (!userStr) return
  const user = JSON.parse(userStr)
  const newTag = asset.tag === 1 ? 0 : 1
  try {
    await favoriteAsset(asset.id, user.id, newTag as 0 | 1)
    asset.tag = newTag
    if (favoritesOnly.value && newTag === 0) {
      assets.value = assets.value.filter(a => a.id !== asset.id)
    }
    ElMessage.success(newTag === 1 ? '已收藏' : '已取消收藏')
  } catch {
    ElMessage.error('操作失败')
  }
}

onMounted(() => {
  loadAssets()
})
</script>

<template>
  <div class="page">
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <div class="container">
      <div class="header">
        <h2 class="title">我的资产</h2>
        <div class="header-right">
          <div class="filter-bar">
            <button class="filter-btn" :class="{ active: activeFilter === 'all' }" @click="setFilter('all')">全部</button>
            <button class="filter-btn" :class="{ active: activeFilter === 'picture' }" @click="setFilter('picture')">图片</button>
            <button class="filter-btn" :class="{ active: activeFilter === 'video' }" @click="setFilter('video')">视频</button>
          </div>
          <button class="filter-btn" :class="{ active: !favoritesOnly }" @click="setFavoritesOnly(false)">生成记录</button>
          <button class="filter-btn" :class="{ active: favoritesOnly }" @click="setFavoritesOnly(true)">收藏</button>
          <button class="refresh-btn" @click="loadAssets()" :disabled="loading">
            <span>{{ loading ? '加载中...' : '刷新' }}</span>
          </button>
        </div>
      </div>

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
          <!-- 视频 -->
          <div
            v-if="isVideo(asset)"
            class="gallery-media video-thumb"
            @click="openVideo(asset)"
          >
            <video :src="getMediaUrl(asset.location)" class="gallery-media" preload="metadata" />
            <div class="video-play-icon">▶</div>
          </div>
          <!-- 图片 -->
          <img
            v-else
            :src="getImageUrl(asset.location)"
            class="gallery-media"
            @click="previewImage(asset)"
          />
          <div class="gallery-info">
            <span class="gallery-name">{{ asset.location.split(/[/\\]/).pop() }}</span>
            <span v-if="isVideo(asset)" class="gallery-type">视频</span>
          </div>
          <button class="download-btn" @click.stop="downloadImage(asset)" title="下载">
            <span>⬇</span>
          </button>
          <button class="favorite-btn" :class="{ favorited: asset.tag === 1 }" @click.stop="toggleFavorite(asset)" title="收藏">
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Image Viewer -->
    <el-image-viewer
      v-if="showImageViewer"
      :url-list="assets.map(a => getImageUrl(a.location))"
      :initial-index="previewInitialIndex"
      @close="closeImageViewer"
      :hide-on-click-modal="true"
    />

    <!-- Video Player 弹窗 -->
    <VideoPlayer
      v-if="activeVideo"
      :visible="showVideoPlayer"
      :src="getMediaUrl(activeVideo.location)"
      :asset-id="activeVideo.id"
      @close="showVideoPlayer = false"
    />
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  position: relative;
  overflow: hidden;
}

.orb {
  position: fixed;
  border-radius: 50%;
  filter: blur(90px);
  pointer-events: none;
  z-index: 0;
  animation: breathe 6s ease-in-out infinite;
}
.orb-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(108,99,255,0.16) 0%, transparent 70%);
  top: -140px; left: 40px;
}
.orb-2 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(167,139,250,0.12) 0%, transparent 70%);
  bottom: -100px; right: 60px;
  animation-delay: 3s;
}

.container {
  position: relative;
  z-index: 1;
  max-width: 1400px;
  margin: 0 auto;
  padding: 40px 20px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 32px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.filter-bar {
  display: flex;
  gap: 8px;
}

.filter-btn {
  padding: 6px 18px;
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.03);
  color: rgba(255,255,255,0.5);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.filter-btn:hover {
  border-color: rgba(108,99,255,0.4);
  color: rgba(255,255,255,0.8);
}
.filter-btn.active {
  background: rgba(108,99,255,0.25);
  border-color: rgba(108,99,255,0.7);
  color: rgba(255,255,255,0.95);
}

.title {
  font-size: 28px;
  font-weight: 600;
  color: rgba(255,255,255,0.9);
  letter-spacing: 2px;
  margin: 0;
}

.refresh-btn {
  padding: 8px 20px;
  border-radius: 8px;
  border: 1px solid rgba(108,99,255,0.3);
  background: rgba(108,99,255,0.1);
  color: rgba(255,255,255,0.8);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.refresh-btn:hover:not(:disabled) {
  background: rgba(108,99,255,0.2);
  border-color: rgba(108,99,255,0.5);
}
.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

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
  border: 1.5px solid rgba(108, 99, 255, 0.5);
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
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
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
  height: 280px;
  object-fit: cover;
  display: block;
  cursor: pointer;
}

.video-thumb {
  position: relative;
  cursor: pointer;
  height: 280px;
  overflow: hidden;
}
.video-thumb video {
  pointer-events: none;
  height: 280px;
}
.video-play-icon {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
  color: rgba(255,255,255,0.85);
  background: rgba(0,0,0,0.3);
  transition: background 0.2s;
}
.video-thumb:hover .video-play-icon {
  background: rgba(0,0,0,0.5);
}

video.gallery-media {
  cursor: default;
  background: #000;
}

.gallery-info {
  padding: 12px 14px;
  background: rgba(0,0,0,0.3);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.gallery-name {
  font-size: 12px;
  color: rgba(255,255,255,0.6);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.gallery-type {
  font-size: 10px;
  color: rgba(167,139,250,0.8);
  background: rgba(167,139,250,0.15);
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}

.download-btn {
  position: absolute;
  bottom: 52px;
  right: 12px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(0,0,0,0.7);
  border: 1px solid rgba(255,255,255,0.2);
  color: white;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.2s;
}
.gallery-item:hover .download-btn {
  opacity: 1;
}
.download-btn:hover {
  background: rgba(108,99,255,0.9);
  transform: scale(1.1);
}

.favorite-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(0,0,0,0.5);
  border: none;
  color: rgba(255,255,255,0.6);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
}
.gallery-item:hover .favorite-btn {
  opacity: 1;
}
.favorite-btn.favorited {
  opacity: 1;
  color: #f43f5e;
  background: rgba(244,63,94,0.15);
}
.favorite-btn.favorited svg { fill: #f43f5e; stroke: #f43f5e; }
.favorite-btn:hover {
  transform: scale(1.15);
  color: #f43f5e;
  background: rgba(244,63,94,0.2);
}

@keyframes breathe {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(0.95); }
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
