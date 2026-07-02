<script setup lang="ts">
interface Asset {
  id: number
  location: string
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
  toggleFavorite: [asset: Asset]
}>()

function getMediaUrl(location: string) {
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
        <span class="gallery-name">{{ asset.location.split(/[/\\]/).pop() }}</span>
        <span v-if="isVideo(asset)" class="gallery-type">视频</span>
      </div>
      <button class="download-btn" @click.stop="emit('download', asset)" title="下载">
        <span>⬇</span>
      </button>
      <button
        class="favorite-btn"
        :class="{ favorited: asset.tag === 1 }"
        @click.stop="emit('toggleFavorite', asset)"
        title="收藏"
      >
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
        </svg>
      </button>
    </div>
  </div>
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
.favorite-btn {
  position: absolute;
  top: 10px; right: 10px;
  width: 32px; height: 32px;
  border-radius: 50%;
  background: rgba(0,0,0,0.5);
  border: none;
  color: rgba(255,255,255,0.6);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  opacity: 0;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
}
.gallery-item:hover .favorite-btn { opacity: 1; }
.favorite-btn.favorited {
  opacity: 1;
  color: #f43f5e;
  background: rgba(244,63,94,0.15);
}
.favorite-btn.favorited svg { fill: #f43f5e; stroke: #f43f5e; }
.favorite-btn:hover { transform: scale(1.15); color: #f43f5e; background: rgba(244,63,94,0.2); }

@keyframes breathe {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(0.95); }
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
