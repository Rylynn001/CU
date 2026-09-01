<script setup lang="ts">
// 历史记录右键菜单 + 生成记录详情弹窗（与资产侧边栏行为一致）
// 父组件通过 open(e, target) 触发；添加到素材时 emit('select', [asset])
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchHistoryByAsset, type HistoryRecord } from '../api/apiService'

withDefaults(defineProps<{
  showAddToMaterial?: boolean
  showReuseParams?: boolean
}>(), {
  showAddToMaterial: true,
  showReuseParams: true,
})

interface MenuTarget {
  assetId: number
  location: string          // 完整 url 或文件路径，供 handleAssetSelect 使用
  asset_type: 'picture' | 'video'
}

const emit = defineEmits<{
  (e: 'select', assets: Array<{ id: number; location: string; asset_type: string }>): void
  (e: 'reuse-params', record: HistoryRecord): void
}>()

const menu = ref<{ visible: boolean; x: number; y: number; target: MenuTarget | null }>({
  visible: false, x: 0, y: 0, target: null,
})

function open(e: MouseEvent, target: MenuTarget) {
  e.preventDefault()
  menu.value = { visible: true, x: e.clientX, y: e.clientY, target }
}
function closeMenu() {
  menu.value.visible = false
}

function addToMaterial() {
  const t = menu.value.target
  closeMenu()
  if (t) emit('select', [{ id: t.assetId, location: t.location, asset_type: t.asset_type }])
}

// ── 查看生成记录弹窗 ──
const showDetail = ref(false)
const detail = ref<HistoryRecord | null>(null)
const loading = ref(false)

async function viewRecord() {
  const t = menu.value.target
  closeMenu()
  if (!t) return
  const userStr = localStorage.getItem('user')
  if (!userStr) { ElMessage.error('请先登录'); return }
  const userId = JSON.parse(userStr).id
  loading.value = true
  try {
    detail.value = await fetchHistoryByAsset(t.assetId, userId)
    showDetail.value = true
  } catch {
    ElMessage.error('未找到该资产对应的生成记录')
  } finally {
    loading.value = false
  }
}

function closeDetail() {
  showDetail.value = false
  setTimeout(() => { detail.value = null }, 300)
}

function reuseParams() {
  if (!detail.value) return
  emit('reuse-params', detail.value)
  closeDetail()
  ElMessage.success('参数已复用到左侧面板')
}

onMounted(() => window.addEventListener('click', closeMenu))
onUnmounted(() => window.removeEventListener('click', closeMenu))

defineExpose({ open })
</script>

<template>
  <!-- 右键菜单 -->
  <Teleport to="body">
    <Transition name="ctx-menu">
      <div
        v-if="menu.visible"
        class="context-menu"
        :style="{ left: menu.x + 'px', top: menu.y + 'px' }"
        @click.stop
      >
        <div v-if="showAddToMaterial" class="context-menu-item" @click="addToMaterial">
          <span class="context-menu-icon">＋</span>
          <span>添加到素材</span>
        </div>
        <div class="context-menu-item" @click="viewRecord">
          <span class="context-menu-icon">◉</span>
          <span>查看生成记录</span>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 生成记录详情弹窗 -->
  <Teleport to="body">
    <Transition name="record-detail">
      <div v-if="showDetail" class="record-detail-overlay" @click="closeDetail">
        <div class="record-detail-modal" @click.stop>
          <div class="modal-header">
            <span class="modal-title">生成记录详情</span>
            <button class="modal-close-btn" @click="closeDetail">✕</button>
          </div>

          <div v-if="detail" class="modal-body">
            <!-- 参考素材 -->
            <div v-if="detail.input_asset_urls && detail.input_asset_urls.length > 0" class="detail-section">
              <div class="section-title">参考素材</div>
              <div class="reference-grid">
                <div v-for="(asset, idx) in detail.input_asset_urls" :key="idx" class="reference-item">
                  <video v-if="asset.type === 'video'" :src="asset.url" class="reference-media" controls />
                  <img v-else :src="asset.url" class="reference-media" />
                  <span class="reference-badge">{{ asset.type === 'video' ? '视频' : '图片' }}{{ idx + 1 }}</span>
                </div>
              </div>
            </div>

            <!-- 提示词 -->
            <div class="detail-section">
              <div class="section-title">提示词</div>
              <div class="prompt-box">{{ detail.prompt || '无' }}</div>
            </div>

            <!-- 模型 -->
            <div class="detail-section">
              <div class="section-title">模型</div>
              <div class="model-tag">{{ detail.model_name || '未知' }}</div>
            </div>

            <!-- 生成参数 -->
            <div class="detail-section">
              <div class="section-title">生成参数</div>
              <div class="param-row">
                <span class="param-label">类型：</span>
                <span class="param-value">{{ detail.type?.includes('video') ? '视频生成' : '图片生成' }}</span>
              </div>
              <div class="param-row" v-if="detail.mode">
                <span class="param-label">模式：</span>
                <span class="param-value">{{ detail.mode === 'img2video' ? '图生视频' : detail.mode === 'txt2video' ? '文生视频' : detail.mode === 'img2img' ? '图生图' : detail.mode === 'txt2img' ? '文生图' : detail.mode }}</span>
              </div>
              <template v-if="detail.payload">
                <div class="param-row" v-if="detail.payload.ratio">
                  <span class="param-label">比例：</span>
                  <span class="param-value">{{ detail.payload.ratio }}</span>
                </div>
                <div class="param-row" v-if="detail.payload.resolution">
                  <span class="param-label">分辨率：</span>
                  <span class="param-value">{{ detail.payload.resolution }}</span>
                </div>
                <div class="param-row" v-if="detail.payload.duration">
                  <span class="param-label">时长：</span>
                  <span class="param-value">{{ detail.payload.duration }}秒</span>
                </div>
                <div class="param-row" v-if="detail.payload.aspect_ratio">
                  <span class="param-label">宽高比：</span>
                  <span class="param-value">{{ detail.payload.aspect_ratio }}</span>
                </div>
                <div class="param-row" v-if="detail.payload.quality">
                  <span class="param-label">质量：</span>
                  <span class="param-value">{{ detail.payload.quality }}</span>
                </div>
                <div class="param-row" v-if="detail.payload.width && detail.payload.height">
                  <span class="param-label">尺寸：</span>
                  <span class="param-value">{{ detail.payload.width }} × {{ detail.payload.height }}</span>
                </div>
                <div class="param-row" v-if="detail.payload.steps">
                  <span class="param-label">采样步数：</span>
                  <span class="param-value">{{ detail.payload.steps }}</span>
                </div>
                <div class="param-row" v-if="detail.payload.cfg">
                  <span class="param-label">CFG：</span>
                  <span class="param-value">{{ detail.payload.cfg }}</span>
                </div>
                <div class="param-row" v-if="detail.payload.sampler_name">
                  <span class="param-label">采样器：</span>
                  <span class="param-value">{{ detail.payload.sampler_name }}</span>
                </div>
                <div class="param-row" v-if="detail.payload.scheduler">
                  <span class="param-label">调度器：</span>
                  <span class="param-value">{{ detail.payload.scheduler }}</span>
                </div>
                <div class="param-row" v-if="detail.payload.seed !== undefined">
                  <span class="param-label">种子：</span>
                  <span class="param-value">{{ detail.payload.seed }}</span>
                </div>
                <div class="param-row" v-if="detail.payload.n || detail.payload.batchSize">
                  <span class="param-label">生成数量：</span>
                  <span class="param-value">{{ detail.payload.n || detail.payload.batchSize }}</span>
                </div>
              </template>
            </div>

            <!-- 生成结果 -->
            <div v-if="detail.output_urls && detail.output_urls.length > 0" class="detail-section">
              <div class="section-title">生成结果</div>
              <div class="output-grid">
                <div v-for="(output, idx) in detail.output_urls" :key="idx" class="output-item">
                  <video v-if="output.type === 'video'" :src="output.url" class="output-media" controls />
                  <img v-else :src="output.url" class="output-media" />
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button class="modal-btn cancel-btn" @click="closeDetail">关闭</button>
            <button v-if="showReuseParams" class="modal-btn reuse-btn" @click="reuseParams">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="1 4 1 10 7 10"/>
                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
              </svg>
              复用参数
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ── 右键菜单 ── */
.context-menu {
  position: fixed;
  z-index: 3000;
  min-width: 140px;
  padding: 5px;
  border-radius: 10px;
  background: rgba(30,30,36,0.95);
  border: 1px solid rgba(255,255,255,0.1);
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  backdrop-filter: blur(12px);
  transform-origin: top left;
}
.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
  color: rgba(255,255,255,0.85);
  cursor: pointer;
  transition: background 0.15s;
}
.context-menu-item:hover { background: rgba(255,255,255,0.1); }
.context-menu-item .context-menu-icon {
  font-size: 13px;
  color: var(--color-muted);
  font-weight: 400;
  line-height: 1;
}
.ctx-menu-enter-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.ctx-menu-leave-active { transition: opacity 0.1s ease, transform 0.1s ease; }
.ctx-menu-enter-from,
.ctx-menu-leave-to {
  opacity: 0;
  transform: scale(0.92);
}

/* ── 生成记录详情弹窗 ── */
.record-detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 3500;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(12px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.record-detail-modal {
  width: 90%;
  max-width: 800px;
  max-height: 85vh;
  background: rgba(25, 25, 30, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 20px;
  box-shadow: 0 25px 80px rgba(0, 0, 0, 0.6);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}
.modal-title {
  font-size: 16px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
  letter-spacing: 0.5px;
}
.modal-close-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: transparent;
  color: rgba(255, 255, 255, 0.5);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.modal-close-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.9);
  transform: rotate(90deg);
}
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.modal-body::-webkit-scrollbar { width: 6px; }
.modal-body::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.03); }
.modal-body::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.16);
  border-radius: 3px;
}
.detail-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.section-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-muted);
  text-transform: uppercase;
  letter-spacing: 1.2px;
}
.reference-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}
.reference-item {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.3);
}
.reference-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.reference-badge {
  position: absolute;
  bottom: 6px;
  left: 6px;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.75);
  color: rgba(255, 255, 255, 0.85);
  font-size: 10px;
  backdrop-filter: blur(4px);
}
.prompt-box {
  padding: 14px 16px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.8);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.model-tag {
  display: inline-flex;
  padding: 8px 16px;
  border-radius: 8px;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--color-border);
  color: var(--color-muted);
  font-size: 13px;
  font-weight: 500;
}
.param-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
}
.param-label {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
  min-width: 60px;
}
.param-value {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
}
.output-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}
.output-item {
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--color-border);
  background: rgba(255,255,255,0.04);
  aspect-ratio: 16 / 9;
}
.output-media {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}
.modal-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid transparent;
}
.cancel-btn {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.6);
}
.cancel-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.9);
}
.reuse-btn {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.24);
  color: rgba(255, 255, 255, 0.95);
}
.reuse-btn:hover {
  border-color: rgba(255, 255, 255, 0.32);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
}
.reuse-btn:active {
  transform: translateY(0);
}
.record-detail-enter-active {
  transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.record-detail-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 1, 1);
}
.record-detail-enter-from,
.record-detail-leave-to {
  opacity: 0;
}
.record-detail-enter-from .record-detail-modal,
.record-detail-leave-to .record-detail-modal {
  opacity: 0;
  transform: scale(0.85) translateY(30px);
}
.record-detail-enter-active .record-detail-modal {
  animation: breathe-in 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes breathe-in {
  0% { opacity: 0; transform: scale(0.85) translateY(30px); }
  50% { transform: scale(1.02) translateY(-5px); }
  100% { opacity: 1; transform: scale(1) translateY(0); }
}
</style>
