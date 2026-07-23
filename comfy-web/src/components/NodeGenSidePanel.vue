<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getApiModels, pollTaskUntilDone, type ApiModel } from '../api/apiService'
import { getCurrentUserId } from '../utils/user'
import { submitImageGeneration, type InputImage } from '../services/imageGenerationService'
import { submitVideoGeneration, submitImg2VideoGeneration } from '../services/videoGenerationService'
import type { SourceAsset, GeneratedAsset } from './NodeGenerateDialog.vue'

const props = defineProps<{
  mode: 'image' | 'video'
  refAssets: SourceAsset[]
  prompt: string
}>()

const emit = defineEmits<{
  close: []
  generated: [asset: GeneratedAsset]
  generating: [value: boolean]
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

async function loadModels() {
  try {
    models.value = await getApiModels(props.mode)
    if (models.value.length && !models.value.some((m) => m.id === modelId.value)) {
      modelId.value = models.value[0].id
    }
  } catch { ElMessage.error('加载模型失败') }
}

onMounted(loadModels)
watch(() => props.mode, loadModels)

async function handleGenerate() {
  if (!modelId.value) { ElMessage.warning('请选择模型'); return }
  if (!props.prompt.trim()) { ElMessage.warning('请输入提示词'); return }
  const userId = getCurrentUserId() ?? undefined
  generating.value = true
  emit('generating', true)
  // 提交后1秒自动收回参数面板，生成在后台继续
  setTimeout(() => emit('close'), 1000)
  try {
    let asset: GeneratedAsset | null = null
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
        const done = await pollTaskUntilDone(result.taskId, userId, 'image')
        const first = done.images?.[0] as { url: string; asset_id?: number } | undefined
        if (first?.asset_id) asset = { id: first.asset_id, url: first.url, isVideo: false }
      } else if (result.images?.length) {
        asset = { id: -Date.now(), url: result.images[0], isVideo: false }
      }
    } else {
      const refIds = props.refAssets.filter((a) => !a.isVideo).map((a) => a.id)
      let taskId: string | undefined
      if (refIds.length > 0) {
        const r = await submitImg2VideoGeneration({
          modelId: modelId.value, prompt: props.prompt,
          ratio: videoRatio.value, resolution: resolution.value, duration: duration.value,
          inputAssetIds: refIds, userId,
        })
        taskId = r.taskId
      } else {
        const r = await submitVideoGeneration({
          modelId: modelId.value, prompt: props.prompt,
          ratio: videoRatio.value, resolution: resolution.value, duration: duration.value, userId,
        })
        taskId = r.taskId
      }
      if (taskId) {
        const done = await pollTaskUntilDone(taskId, userId, 'video')
        const first = done.images?.[0] as { url: string; asset_id?: number } | undefined
        if (first?.asset_id) asset = { id: first.asset_id, url: first.url, isVideo: true }
      }
    }
    if (asset) { emit('generated', asset); ElMessage.success('生成完成') }
    else ElMessage.error('生成结果无效')
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    generating.value = false
    emit('generating', false)
  }
}
</script>

<template>
  <div class="gsp-panel">
    <!-- 头部 -->
    <div class="gsp-header">
      <span class="gsp-title">{{ generating ? (mode === 'video' ? '视频生成中' : '图片生成中') : (mode === 'video' ? '视频生成' : '图片生成') }}</span>
      <button class="gsp-close" @click="emit('close')">✕</button>
    </div>

    <div class="gsp-body">
      <!-- 已选参考图 -->
      <div class="gsp-section">
        <div class="gsp-label">
          参考图
          <span class="gsp-hint">{{ refAssets.length ? `已选 ${refAssets.length} 张` : '点击上方面板图片选择' }}</span>
        </div>
        <div v-if="refAssets.length" class="gsp-refs">
          <div v-for="a in refAssets" :key="a.id" class="gsp-ref-thumb">
            <img :src="a.url" />
          </div>
        </div>
        <div v-else class="gsp-ref-empty">点击上方面板图片选择</div>
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
        <textarea v-model="localPrompt" class="gsp-textarea" rows="4" placeholder="描述你想生成的内容" />
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
      <button class="gsp-generate" :disabled="generating" @click="handleGenerate">
        <span v-if="generating" class="gsp-spin" />
        {{ generating ? '生成中...' : '开始生成' }}
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
  width: 54px; height: 54px;
  border-radius: 7px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.3);
}
.gsp-ref-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
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
  font-size: 12px;
  outline: none;
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
