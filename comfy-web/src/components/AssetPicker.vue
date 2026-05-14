<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

interface Asset {
  id: number
  location: string
  asset_type?: string
}

const props = defineProps<{
  visible: boolean
  maxSelect?: number
  allowVideo?: boolean
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'select': [assets: Array<{ id: number; location: string; asset_type?: string }>]
}>()

const assets = ref<Asset[]>([])
const loading = ref(false)
const selectedAssets = ref<Asset[]>([])
const activeFilter = ref<'all' | 'picture' | 'video'>('all')

const showImageViewer = ref(false)
const previewImageUrl = ref('')

function previewImage(location: string) {
  previewImageUrl.value = getImageUrl(location)
  showImageViewer.value = true
}

async function loadAssets(assetType?: 'picture' | 'video') {
  const userStr = localStorage.getItem('user')
  if (!userStr) { ElMessage.error('请先登录'); return }
  const user = JSON.parse(userStr)
  loading.value = true
  try {
    const url = assetType
      ? `/api/api-proxy/user/assets?user_id=${user.id}&asset_type=${assetType}`
      : `/api/api-proxy/user/assets?user_id=${user.id}`
    const res = await fetch(url)
    if (!res.ok) throw new Error('加载失败')
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
  return `/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
}

function selectAsset(asset: Asset) {
  if (!props.allowVideo && asset.asset_type === 'video') {
    ElMessage.warning('当前不支持选择视频')
    return
  }
  const max = props.maxSelect ?? 1
  const idx = selectedAssets.value.findIndex(a => a.id === asset.id)
  if (idx >= 0) {
    selectedAssets.value.splice(idx, 1)
  } else if (selectedAssets.value.length < max) {
    selectedAssets.value.push(asset)
  } else {
    ElMessage.warning(`最多只能选择 ${max} 个素材`)
  }
}

function confirmSelect() {
  if (selectedAssets.value.length === 0) { ElMessage.warning('请先选择素材'); return }
  emit('select', selectedAssets.value.map(a => ({ id: a.id, location: a.location, asset_type: a.asset_type })))
  emit('update:visible', false)
  selectedAssets.value = []
}

function cancel() {
  emit('update:visible', false)
  selectedAssets.value = []
}

function downloadAsset(asset: Asset) {
  const a = document.createElement('a')
  a.href = getImageUrl(asset.location)
  a.download = asset.location
  a.click()
}

function downloadPreviewImage() {
  const a = document.createElement('a')
  a.href = previewImageUrl.value
  a.download = 'asset.png'
  a.click()
}

watch(() => props.visible, (val) => {
  if (val) {
    activeFilter.value = 'all'
    loadAssets()
  }
})
</script>

<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="emit('update:visible', $event)"
    title="选择资产"
    width="800px"
    :before-close="cancel"
  >
    <!-- 筛选按钮 -->
    <div class="filter-bar">
      <button class="filter-btn" :class="{ active: activeFilter === 'all' }" @click="setFilter('all')">全部</button>
      <button class="filter-btn" :class="{ active: activeFilter === 'picture' }" @click="setFilter('picture')">图片</button>
      <button class="filter-btn" :class="{ active: activeFilter === 'video' }" @click="setFilter('video')">视频</button>
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
      <p class="empty-text">{{ activeFilter === 'all' ? '暂无资产' : '该分类暂无内容' }}</p>
    </div>

    <div v-else class="gallery">
      <div
        v-for="asset in assets"
        :key="asset.id"
        class="gallery-item"
        :class="{ selected: selectedAssets.some(a => a.id === asset.id) }"
      >
        <video
          v-if="asset.asset_type === 'video'"
          :src="getMediaUrl(asset.location)"
          class="gallery-image"
          @click="selectAsset(asset)"
          loading="lazy"
        />
        <img
          v-else
          :src="getImageUrl(asset.location)"
          class="gallery-image"
          @click="selectAsset(asset)"
          @dblclick="previewImage(asset.location)"
          loading="lazy"
        />
        <div class="gallery-info">
          <span class="gallery-name">{{ asset.location.split(/[/\\]/).pop() }}</span>
          <span v-if="asset.asset_type === 'video'" class="asset-type-badge">视频</span>
        </div>
        <div v-if="selectedAssets.some(a => a.id === asset.id)" class="selected-badge">
          {{ selectedAssets.findIndex(a => a.id === asset.id) + 1 }}
        </div>
        <button class="download-btn" @click.stop="downloadAsset(asset)" title="下载">⬇</button>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <span class="select-count">已选 {{ selectedAssets.length }}{{ maxSelect && maxSelect > 1 ? ` / ${maxSelect}` : '' }} 个</span>
        <button class="cancel-btn" @click="cancel">取消</button>
        <button class="confirm-btn" @click="confirmSelect" :disabled="selectedAssets.length === 0">确认选择</button>
      </div>
    </template>

    <!-- 图片预览弹窗 -->
    <el-dialog
      v-model="showImageViewer"
      :show-close="true"
      :close-on-click-modal="true"
      width="90%"
      class="preview-dialog"
      :append-to-body="true"
    >
      <div class="preview-container" @wheel.prevent.stop>
        <img :src="previewImageUrl" class="preview-image" @wheel.prevent.stop />
        <button class="preview-download-btn" @click="downloadPreviewImage">⬇ 下载</button>
      </div>
    </el-dialog>
  </el-dialog>
</template>

<style scoped>
.filter-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.filter-btn {
  padding: 5px 20px;
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.03);
  color: rgba(255,255,255,0.45);
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

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  padding: 60px 0;
}
.loading-text {
  font-size: 13px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 2px;
}

.breath-ring {
  position: relative;
  width: 80px; height: 80px;
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
  padding: 60px 0;
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
  color: rgba(255,255,255,0.4);
  letter-spacing: 2px;
}

.gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 16px;
  max-height: 460px;
  overflow-y: auto;
  padding: 4px;
}

.gallery-item {
  position: relative;
  border-radius: 10px;
  overflow: hidden;
  background: rgba(255,255,255,0.03);
  border: 2px solid rgba(255,255,255,0.08);
  transition: border-color 0.2s;
  cursor: pointer;
}
.gallery-item:hover { border-color: rgba(108,99,255,0.3); }
.gallery-item.selected {
  border-color: rgba(108,99,255,0.8);
  box-shadow: 0 0 20px rgba(108,99,255,0.3);
}

.gallery-image {
  width: 100%;
  height: 160px;
  object-fit: cover;
  display: block;
}

.gallery-info {
  padding: 8px 10px;
  background: rgba(0,0,0,0.3);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.gallery-name {
  font-size: 11px;
  color: rgba(255,255,255,0.6);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.asset-type-badge {
  font-size: 10px;
  color: rgba(167,139,250,0.8);
  background: rgba(167,139,250,0.15);
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.selected-badge {
  position: absolute;
  top: 8px; right: 8px;
  width: 28px; height: 28px;
  border-radius: 50%;
  background: rgba(108,99,255,0.95);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: bold;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

.download-btn {
  position: absolute;
  bottom: 36px; right: 8px;
  width: 32px; height: 32px;
  border-radius: 50%;
  background: rgba(0,0,0,0.7);
  border: 1px solid rgba(255,255,255,0.2);
  color: white;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.2s;
}
.gallery-item:hover .download-btn { opacity: 1; }
.download-btn:hover { background: rgba(108,99,255,0.9); transform: scale(1.1); }

.dialog-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  align-items: center;
}
.select-count {
  font-size: 12px;
  color: rgba(255,255,255,0.35);
  margin-right: auto;
}

.cancel-btn, .confirm-btn {
  padding: 8px 24px;
  border-radius: 8px;
  border: none;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.cancel-btn {
  background: rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.7);
}
.cancel-btn:hover { background: rgba(255,255,255,0.12); }
.confirm-btn {
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  color: white;
  font-weight: 500;
}
.confirm-btn:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }
.confirm-btn:disabled { opacity: 0.4; cursor: not-allowed; }

@keyframes breathe {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(0.95); }
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.preview-dialog :deep(.el-dialog__body) {
  padding: 0;
  background: #000;
}
.preview-container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  background: #000;
}
.preview-image {
  max-width: 100%;
  max-height: 80vh;
  object-fit: contain;
}
.preview-download-btn {
  position: absolute;
  bottom: 20px; right: 20px;
  padding: 10px 20px;
  background: rgba(108,99,255,0.9);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}
.preview-download-btn:hover { background: rgba(108,99,255,1); transform: translateY(-2px); }
</style>
