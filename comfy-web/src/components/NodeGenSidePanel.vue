<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { getApiModels, pollTaskUntilDone, type ApiModel } from '../api/apiService'
import { getCurrentUserId } from '../utils/user'
import { submitImageGeneration, type InputImage } from '../services/imageGenerationService'
import { submitVideoGeneration, submitImg2VideoGeneration } from '../services/videoGenerationService'
import { useAtMention } from '../composables/useAtMention'
import type { SourceAsset, GeneratedAsset } from './NodeGenerateDialog.vue'

export interface NodeGenerationRequest {
  mode: 'image' | 'video'
  prompt: string
  settings: Record<string, unknown>
}

const props = withDefaults(defineProps<{
  mode: 'image' | 'video'
  refAssets: SourceAsset[]
  prompt: string
  settings?: Record<string, unknown>
  viewOnly?: boolean
  errorMessage?: string
  handoffOnGenerate?: boolean
  autoGenerate?: boolean
}>(), {
  handoffOnGenerate: false,
  autoGenerate: false,
})

const emit = defineEmits<{
  close: []
  generated: [assets: GeneratedAsset[]]
  generating: [value: boolean]
  submitted: [historyId: number]
  failed: [message: string]
  'generate-request': [request: NodeGenerationRequest]
  'remove-ref': [id: number]
  'update:prompt': [value: string]
}>()

const models = ref<ApiModel[]>([])
const modelId = ref('')
const generating = ref(false)

const aspectRatio = ref('1:1')
const quality = ref('high')
const batchSize = ref(1)
const RATIOS = ['1:1', '16:9', '9:16', '4:3', '3:4']
const QUALITIES = [{ v: 'low', label: '低' }, { v: 'medium', label: '中' }, { v: 'high', label: '高' }]

const videoRatio = ref('16:9')
const resolution = ref('720p')
const duration = ref(8)
const VIDEO_RATIOS = ['16:9', '4:3', '1:1', '3:4', '9:16']
const RESOLUTIONS = ['480p', '720p', '1080p']

const localPrompt = computed({
  get: () => props.prompt,
  set: (v) => emit('update:prompt', v),
})
const promptInputRef = ref<HTMLTextAreaElement | null>(null)
const mentionItems = computed(() => props.refAssets.map((asset) => ({
  url: asset.url,
  type: asset.isVideo ? 'video' as const : 'image' as const,
})))
const {
  atMentionActive,
  atMentionIndex,
  onPromptKeyup,
  onPromptKeydown,
  insertMention,
  closeMention,
} = useAtMention(
  () => props.prompt,
  (value) => emit('update:prompt', value),
  () => mentionItems.value,
  promptInputRef,
)

function getMentionLabel(asset: SourceAsset, index: number) {
  return asset.isVideo ? `@视频${index + 1}` : `@图${index + 1}`
}

async function loadModels() {
  try {
    models.value = (await getApiModels(props.mode)).map((model) => ({
      ...model,
      id: String(model.id),
    }))
    if (models.value.length && !models.value.some((m) => m.id === modelId.value)) {
      modelId.value = models.value[0].id
    }
  } catch { ElMessage.error('加载模型失败') }
}

function applySettings() {
  const settings = props.settings
  if (!settings) return
  if (settings.model != null) modelId.value = String(settings.model)
  if (typeof settings.aspect_ratio === 'string') aspectRatio.value = settings.aspect_ratio
  if (typeof settings.quality === 'string') quality.value = settings.quality
  if (typeof settings.n === 'number') batchSize.value = settings.n
  if (typeof settings.ratio === 'string') videoRatio.value = settings.ratio
  if (typeof settings.resolution === 'string') resolution.value = settings.resolution
  if (typeof settings.duration === 'number') duration.value = settings.duration
}

onMounted(async () => {
  applySettings()
  await loadModels()
  if (props.autoGenerate) {
    await nextTick()
    void handleGenerate()
  }
})
watch(() => props.mode, loadModels)
watch(() => props.settings, applySettings, { deep: true })

async function handleGenerate() {
  if (!modelId.value) { ElMessage.warning('请选择模型'); return }
  if (!props.prompt.trim()) { ElMessage.warning('请输入提示词'); return }
  if (props.handoffOnGenerate) {
    emit('generate-request', {
      mode: props.mode,
      prompt: props.prompt,
      settings: props.mode === 'image'
        ? { model: Number(modelId.value), aspect_ratio: aspectRatio.value, quality: quality.value, n: batchSize.value }
        : { model: Number(modelId.value), ratio: videoRatio.value, resolution: resolution.value, duration: duration.value },
    })
    return
  }
  const userId = getCurrentUserId() ?? undefined
  generating.value = true
  emit('generating', true)
  // 提交后1秒自动收回参数面板，生成在后台继续
  setTimeout(() => emit('close'), 1000)
  try {
    const assets: GeneratedAsset[] = []
    if (props.mode === 'image') {
      const inputImages: InputImage[] = props.refAssets.filter((a) => !a.isVideo).map((a) => ({
        file: null, preview: a.url, assetLocation: '', assetId: a.id,
      }))
      const result = await submitImageGeneration({
        modelId: Number(modelId.value), prompt: props.prompt,
        aspect_ratio: aspectRatio.value, quality: quality.value, batchSize: batchSize.value,
        img2img: inputImages.length > 0, inputImages, userId,
      })
      if (result.taskId) {
        if (result.historyId) emit('submitted', result.historyId)
        const done = await pollTaskUntilDone(result.taskId, userId, 'image')
        done.images?.forEach((item, index) => {
          const output = item as { url: string; asset_id?: number }
          if (output.url) {
            assets.push({
              id: output.asset_id ?? -(Date.now() + index),
              url: output.url,
              isVideo: false,
            })
          }
        })
      } else if (result.images?.length) {
        result.images.forEach((url, index) => {
          assets.push({ id: -(Date.now() + index), url, isVideo: false })
        })
      }
    } else {
      const refIds = props.refAssets.map((a) => a.id)
      let taskId: string | undefined
      let historyId: number | undefined
      if (refIds.length > 0) {
        const r = await submitImg2VideoGeneration({
          modelId: Number(modelId.value), prompt: props.prompt,
          ratio: videoRatio.value, resolution: resolution.value, duration: duration.value,
          inputAssetIds: refIds, userId,
        })
        taskId = r.taskId
        historyId = r.historyId
      } else {
        const r = await submitVideoGeneration({
          modelId: Number(modelId.value), prompt: props.prompt,
          ratio: videoRatio.value, resolution: resolution.value, duration: duration.value, userId,
        })
        taskId = r.taskId
        historyId = r.historyId
      }
      if (taskId) {
        if (historyId) emit('submitted', historyId)
        const done = await pollTaskUntilDone(taskId, userId, 'video')
        done.images?.forEach((item, index) => {
          const output = item as { url: string; asset_id?: number }
          if (output.url) {
            assets.push({
              id: output.asset_id ?? -(Date.now() + index),
              url: output.url,
              isVideo: true,
            })
          }
        })
      }
    }
    if (assets.length) { emit('generated', assets); ElMessage.success(`生成完成，共 ${assets.length} 个结果`) }
    else ElMessage.error('生成结果无效')
  } catch (e: any) {
    const message = e?.message || '生成失败'
    emit('failed', message)
    ElMessage.error(message)
  } finally {
    generating.value = false
    emit('generating', false)
  }
}
</script>

<template>
  <div class="gsp-panel" :class="{ 'is-view-only': viewOnly }">
    <!-- 头部 -->
    <div class="gsp-header">
      <span class="gsp-title">{{ errorMessage ? (mode === 'video' ? '视频生成失败' : '图片生成失败') : ((generating || viewOnly) ? (mode === 'video' ? '视频生成中' : '图片生成中') : (mode === 'video' ? '视频生成' : '图片生成')) }}</span>
      <button class="gsp-close" @click="emit('close')">✕</button>
    </div>

    <div class="gsp-body">
      <div v-if="errorMessage" class="gsp-error">{{ errorMessage }}</div>
      <!-- 已选参考素材 -->
      <div class="gsp-section">
        <div class="gsp-label">
          {{ mode === 'image' ? '参考图' : '参考素材' }}
          <span class="gsp-hint">{{ refAssets.length ? `已选 ${refAssets.length} 项` : (mode === 'image' ? '点击或拖入第一面板图片' : '点击或拖入第一面板素材') }}</span>
        </div>
        <div v-if="refAssets.length" class="gsp-refs">
          <div v-for="a in refAssets" :key="a.id" class="gsp-ref-thumb">
            <video v-if="a.isVideo" :src="a.url" muted playsinline preload="metadata" />
            <img v-else :src="a.url" />
            <button
              type="button"
              class="gsp-ref-remove"
              title="移除参考素材"
              :aria-label="`移除参考素材 ${a.id}`"
              :disabled="generating"
              @click="emit('remove-ref', a.id)"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </div>
        <div v-else class="gsp-ref-empty">
          {{ mode === 'image' ? '点击第一面板图片，或拖动图片到参数面板' : '点击第一面板素材，或拖动素材到参数面板' }}
        </div>
      </div>

      <!-- 模型 -->
      <div class="gsp-section">
        <div class="gsp-label">模型</div>
        <select v-model="modelId" class="gsp-select">
          <option v-for="m in models" :key="m.id" :value="m.id">{{ m.description || m.name }}</option>
        </select>
      </div>

      <!-- 提示词 -->
      <div class="gsp-section">
        <div class="gsp-label">提示词</div>
        <div class="gsp-prompt-wrap">
          <textarea
            ref="promptInputRef"
            v-model="localPrompt"
            class="gsp-textarea"
            rows="4"
            placeholder="描述你想生成的内容（输入 @ 引用参考素材）"
            @keyup="onPromptKeyup"
            @keydown="onPromptKeydown"
            @blur="closeMention"
          />
          <div v-if="atMentionActive && refAssets.length" class="gsp-mention-dropdown">
            <button
              v-for="(asset, index) in refAssets"
              :key="asset.id"
              type="button"
              class="gsp-mention-item"
              :class="{ active: atMentionIndex === index }"
              @mousedown.prevent="insertMention(index)"
            >
              <video v-if="asset.isVideo" :src="asset.url" muted playsinline preload="metadata" />
              <img v-else :src="asset.url" />
              <span>{{ getMentionLabel(asset, index) }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 图片专有参数 -->
      <template v-if="mode === 'image'">
        <div class="gsp-section">
          <div class="gsp-label">宽高比</div>
          <div class="gsp-chips">
            <button
              v-for="r in RATIOS" :key="r"
              class="gsp-chip" :class="{ active: aspectRatio === r }"
              @click="aspectRatio = r"
            >{{ r }}</button>
          </div>
        </div>
        <div class="gsp-section">
          <div class="gsp-label">质量</div>
          <div class="gsp-chips">
            <button
              v-for="q in QUALITIES" :key="q.v"
              class="gsp-chip" :class="{ active: quality === q.v }"
              @click="quality = q.v"
            >{{ q.label }}</button>
          </div>
        </div>
        <div class="gsp-section">
          <div class="gsp-label">数量 <span class="gsp-val">{{ batchSize }}</span></div>
          <input type="range" v-model.number="batchSize" min="1" max="4" step="1" class="gsp-range" />
        </div>
      </template>

      <!-- 视频专有参数 -->
      <template v-else>
        <div class="gsp-section">
          <div class="gsp-label">视频比例</div>
          <div class="gsp-chips">
            <button
              v-for="r in VIDEO_RATIOS" :key="r"
              class="gsp-chip" :class="{ active: videoRatio === r }"
              @click="videoRatio = r"
            >{{ r }}</button>
          </div>
        </div>
        <div class="gsp-section">
          <div class="gsp-label">分辨率</div>
          <div class="gsp-chips">
            <button
              v-for="res in RESOLUTIONS" :key="res"
              class="gsp-chip" :class="{ active: resolution === res }"
              @click="resolution = res"
            >{{ res }}</button>
          </div>
        </div>
        <div class="gsp-section">
          <div class="gsp-label">时长 <span class="gsp-val">{{ duration }}s</span></div>
          <input type="range" v-model.number="duration" min="1" max="60" step="1" class="gsp-range" />
        </div>
      </template>
    </div>

    <!-- 生成按钮 -->
    <div class="gsp-footer">
      <button class="gsp-generate" :disabled="generating || viewOnly" @click="handleGenerate">
        <span v-if="generating" class="gsp-spin" />
        {{ errorMessage ? '生成失败' : ((generating || viewOnly) ? '生成中...' : '开始生成') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.gsp-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: linear-gradient(180deg, rgba(18, 21, 30, 0.97), rgba(6, 8, 13, 0.96));
  backdrop-filter: var(--glass-blur);
  overflow: hidden;
}
.is-view-only .gsp-body {
  pointer-events: none;
}
.gsp-error {
  margin: 12px 16px 0;
  padding: 10px 12px;
  border: 1px solid rgba(255, 104, 104, 0.36);
  border-radius: 6px;
  background: rgba(255, 80, 80, 0.1);
  color: rgba(255, 172, 172, 0.95);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
}
.gsp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 12px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.gsp-title {
  font-size: 13px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
}
.gsp-close {
  width: 22px; height: 22px;
  border-radius: 6px; border: none;
  background: transparent;
  color: rgba(255,255,255,0.3);
  font-size: 12px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.gsp-close:hover { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.8); }

.gsp-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.gsp-body::-webkit-scrollbar { width: 4px; }
.gsp-body::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

.gsp-section { display: flex; flex-direction: column; gap: 6px; }
.gsp-label {
  font-size: 11px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.gsp-hint { color: rgba(255,255,255,0.22); font-size: 10px; }
.gsp-val { color: rgba(255,255,255,0.6); }

/* 参考图 */
.gsp-refs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.gsp-ref-thumb {
  position: relative;
  width: 54px; height: 54px;
  border-radius: 7px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.3);
}
.gsp-ref-thumb img,
.gsp-ref-thumb video { width: 100%; height: 100%; object-fit: cover; display: block; }
.gsp-ref-remove {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 18px;
  height: 18px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: 50%;
  background: rgba(6, 8, 13, 0.82);
  color: rgba(255, 255, 255, 0.78);
  cursor: pointer;
  opacity: 0.72;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}
.gsp-ref-thumb:hover .gsp-ref-remove,
.gsp-ref-remove:focus-visible {
  opacity: 1;
}
.gsp-ref-remove:hover:not(:disabled) {
  background: rgba(220, 38, 38, 0.82);
  color: #fff;
}
.gsp-ref-remove:disabled { cursor: not-allowed; }
.gsp-ref-empty {
  font-size: 11px;
  color: rgba(255,255,255,0.2);
  padding: 8px 0;
  letter-spacing: 0.3px;
}

/* 控件 */
.gsp-select {
  width: 100%;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.05);
  color: rgba(255,255,255,0.8);
  color-scheme: dark;
  font-size: 12px;
  outline: none;
}
.gsp-select option {
  background: #12151e;
  color: rgba(255,255,255,0.86);
}
.gsp-textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 9px 10px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.05);
  color: rgba(255,255,255,0.8);
  font-size: 12px;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s;
}
.gsp-textarea:focus { border-color: rgba(255, 255, 255, 0.28); }

.gsp-prompt-wrap {
  position: relative;
}
.gsp-mention-dropdown {
  position: absolute;
  top: calc(100% + 5px);
  left: 0;
  right: 0;
  z-index: 20;
  max-height: 176px;
  overflow-y: auto;
  padding: 4px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 7px;
  background: rgba(8, 10, 16, 0.98);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.42);
}
.gsp-mention-item {
  width: 100%;
  height: 42px;
  padding: 5px 7px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: rgba(255, 255, 255, 0.72);
  font-size: 11px;
  text-align: left;
  cursor: pointer;
}
.gsp-mention-item:hover,
.gsp-mention-item.active {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}
.gsp-mention-item img,
.gsp-mention-item video {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  border-radius: 4px;
  object-fit: cover;
}

.gsp-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.gsp-chip {
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.04);
  color: rgba(255,255,255,0.5);
  font-size: 11px; cursor: pointer;
  transition: all 0.15s;
}
.gsp-chip:hover { border-color: rgba(255,255,255,0.2); color: rgba(255,255,255,0.8); }
.gsp-chip.active {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.32);
  color: #fff;
}

.gsp-range {
  width: 100%;
  accent-color: rgba(255, 255, 255, 0.8);
}

/* 底部生成按钮 */
.gsp-footer {
  flex-shrink: 0;
  padding: 12px 14px;
  border-top: 1px solid rgba(255,255,255,0.06);
}
.gsp-generate {
  width: 100%;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.gsp-generate:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.18);
  border-color: rgba(255, 255, 255, 0.45);
}
.gsp-generate:disabled { opacity: 0.45; cursor: not-allowed; }

.gsp-spin {
  width: 14px; height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: #fff;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
