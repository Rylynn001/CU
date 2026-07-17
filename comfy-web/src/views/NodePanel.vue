<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AssetSidebar from '../components/AssetSidebar.vue'
import CircularGallery from '../components/CircularGallery.vue'

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

const panelStyles = computed(() => panels.value.map((panel) => ({
  flexGrow: panel.ratio,
  flexBasis: 0,
})))

const galleryItems = computed(() => panels.value.map((panel) => (
  panel.assets
    .filter((asset) => !isVideo(asset))
    .map((asset) => ({
      image: getMediaUrl(asset.location),
      text: asset.location.split(/[/\\]/).pop() || `资产 ${asset.id}`,
    }))
)))

const selectedAssets = computed(() => {
  const assets = new Map<number, Asset>()
  panels.value.forEach((panel) => {
    panel.assets.forEach((asset) => assets.set(asset.id, asset))
  })
  return Array.from(assets.values())
})

function getMediaUrl(location: string) {
  return `/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
}

function isVideo(asset: Asset) {
  const ext = asset.location.split('.').pop()?.toLowerCase()
  return ['mp4', 'mov', 'avi', 'webm'].includes(ext || '')
}

function addAssetToPanel(asset: Asset) {
  if (isVideo(asset)) {
    ElMessage.warning('节点面板预览暂只支持图片资产')
    return
  }

  panels.value.forEach((panel) => {
    if (!panel.assets.some((item) => item.id === asset.id)) {
      panel.assets.push(asset)
    }
  })
  ElMessage.success('已添加到节点面板')
}

function removeAsset(asset: Asset) {
  panels.value.forEach((panel) => {
    panel.assets = panel.assets.filter((item) => item.id !== asset.id)
  })
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
  <div class="node-panel-page">
    <div class="node-orb node-orb-2" />

    <main class="panel-workspace">
      <section class="panel-shell" aria-label="节点预览面板">
        <div class="panel-stack">
          <template v-for="(panel, index) in panels" :key="index">
            <article class="preview-panel" :style="panelStyles[index]">
              <CircularGallery
                :items="galleryItems[index]"
                :bend="0"
                text-color="#ffffff"
                :border-radius="0.05"
                :scroll-ease="0.05"
                font-url=""
                font="bold 30px Orbitron"
                :scroll-speed="3"
              />
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

        <div v-if="selectedAssets.length > 0" class="asset-dock">
          <button
            v-for="asset in selectedAssets"
            :key="asset.id"
            type="button"
            class="asset-pill"
            :title="asset.location.split(/[/\\]/).pop()"
            @click="removeAsset(asset)"
          >
            <img :src="getMediaUrl(asset.location)" alt="" />
            <span>{{ asset.location.split(/[/\\]/).pop() }}</span>
          </button>
        </div>
      </section>

      <AssetSidebar @select="addAssetToPanel" />
    </main>
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

.asset-dock {
  position: absolute;
  left: 14px;
  right: 14px;
  bottom: 12px;
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(18px);
}

.asset-pill {
  width: 124px;
  height: 36px;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px 4px 4px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.07);
  color: rgba(255, 255, 255, 0.76);
  cursor: pointer;
}

.asset-pill:hover {
  border-color: rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.12);
}

.asset-pill img {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  object-fit: cover;
  flex-shrink: 0;
}

.asset-pill span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
}

</style>
