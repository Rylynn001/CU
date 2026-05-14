<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElImageViewer } from 'element-plus'

interface Asset {
  id: number
  location: string
  asset_type?: string
}

const assets = ref<Asset[]>([])
const loading = ref(false)
const activeFilter = ref<'all' | 'picture' | 'video'>('all')

// 图片预览
const showImageViewer = ref(false)
const previewImageUrl = ref('')
const previewInitialIndex = ref(0)

function previewImage(asset: Asset) {
  // 视频不支持预览
  if (isVideo(asset)) return

  const index = assets.value.findIndex(a => a.id === asset.id)
  previewInitialIndex.value = index >= 0 ? index : 0
  previewImageUrl.value = getImageUrl(asset.location)
  showImageViewer.value = true
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
    const url = assetType
      ? `/api/api-proxy/user/assets?user_id=${user.id}&asset_type=${assetType}`
      : `/api/api-proxy/user/assets?user_id=${user.id}`
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

function getImageUrl(location: string) {
  return `/api/view?filename=${encodeURIComponent(location)}&type=output`
}

function getMediaUrl(location: string) {
  return `/api/api-proxy/output/${location.split('\\').pop()}`
}

function isVideo(asset: Asset): boolean {
  const ext = asset.location.split('.').pop()?.toLowerCase()
  return ['mp4', 'mov', 'avi', 'webm'].includes(ext || '')
}

function downloadImage(asset: Asset) {
  const url = isVideo(asset) ? getMediaUrl(asset.location) : getImageUrl(asset.location)
  const a = document.createElement('a')
  a.href = url
  a.download = asset.location.split('\\').pop() || 'asset'
  a.click()
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
          <video
            v-if="isVideo(asset)"
            :src="getMediaUrl(asset.location)"
            class="gallery-media"
            controls
          />
          <!-- 图片 -->
          <img
            v-else
            :src="getImageUrl(asset.location)"
            class="gallery-media"
            @click="previewImage(asset)"
          />
          <div class="gallery-info">
            <span class="gallery-name">{{ asset.location.split('\\').pop() }}</span>
            <span v-if="isVideo(asset)" class="gallery-type">视频</span>
          </div>
          <button class="download-btn" @click.stop="downloadImage(asset)" title="下载">
            <span>⬇</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Image Viewer -->
    <el-image-viewer
      v-if="showImageViewer"
      :url-list="assets.map(a => getImageUrl(a.location))"
      :initial-index="previewInitialIndex"
      @close="showImageViewer = false"
      :hide-on-click-modal="true"
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

@keyframes breathe {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(0.95); }
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
