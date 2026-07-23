<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getApiModels, pollTaskUntilDone, type ApiModel } from '../api/apiService'
import { getCurrentUserId } from '../utils/user'
import { submitImageGeneration, type InputImage } from '../services/imageGenerationService'
import { submitVideoGeneration, submitImg2VideoGeneration } from '../services/videoGenerationService'

// 供参考图勾选用的资产（来自上一个面板）
export interface SourceAsset {
  id: number
  url: string
  isVideo: boolean
}

// 生成完成后回传给面板的新资产
export interface GeneratedAsset {
  id: number
  url: string
  isVideo: boolean
}

const props = defineProps<{
  mode: 'image' | 'video'
  visible: boolean
  sourceAssets: SourceAsset[]
}>()

const emit = defineEmits<{
  close: []
  generated: [asset: GeneratedAsset]
}>()

const models = ref<ApiModel[]>([])
const modelId = ref('')
const prompt = ref('')
const generating = ref(false)

// 图片参数
const aspectRatio = ref('1:1')
const quality = ref('high')
const batchSize = ref(1)
const RATIOS = ['1:1', '16:9', '9:16', '4:3', '3:4']
const QUALITIES = ['low', 'medium', 'high']

// 视频参数
const ratio = ref('16:9')
const resolution = ref('720p')
const duration = ref(8)
const VIDEO_RATIOS = ['16:9', '4:3', '1:1', '3:4', '9:16']
const RESOLUTIONS = ['480p', '720p', '1080p']

// 只有图片资产可作参考图
const refCandidates = computed(() => props.sourceAssets.filter((a) => !a.isVideo))
const selectedRefIds = ref<number[]>([])

function toggleRef(id: number) {
  const i = selectedRefIds.value.indexOf(id)
  if (i >= 0) selectedRefIds.value.splice(i, 1)
  else selectedRefIds.value.push(id)
}

// 打开时加载模型、重置勾选
watch(
  () => props.visible,
  async (v) => {
    if (!v) return
    selectedRefIds.value = []
    try {
      models.value = await getApiModels(props.mode)
      if (models.value.length && !models.value.some((m) => m.id === modelId.value)) {
        modelId.value = models.value[0].id
      }
    } catch {
      ElMessage.error('加载模型失败')
    }
  },
)

async function handleGenerate() {
  if (!modelId.value) { ElMessage.warning('请选择模型'); return }
  if (!prompt.value.trim()) { ElMessage.warning('请输入提示词'); return }

  const userId = getCurrentUserId() ?? undefined
  const refs = refCandidates.value.filter((a) => selectedRefIds.value.includes(a.id))
  generating.value = true

  try {
    let asset: GeneratedAsset | null = null

    if (props.mode === 'image') {
      const inputImages: InputImage[] = refs.map((a) => ({
        file: null, preview: a.url, assetLocation: '', assetId: a.id,
      }))
      const result = await submitImageGeneration({
        modelId: Number(modelId.value),
        prompt: prompt.value,
        aspect_ratio: aspectRatio.value,
        quality: quality.value,
        batchSize: batchSize.value,
        img2img: refs.length > 0,
        inputImages,
        userId,
      })
      if (result.taskId) {
        const done = await pollTaskUntilDone(result.taskId, userId, 'image')
        const first = done.images?.[0] as { url: string; asset_id?: number } | undefined
        if (first?.asset_id) asset = { id: first.asset_id, url: first.url, isVideo: false }
      } else if (result.images?.length) {
        // 同步返回无 asset_id，用负数占位（不可溯源）
        asset = { id: -Date.now(), url: result.images[0], isVideo: false }
      }
    } else {
      let taskId: string | undefined
      if (refs.length > 0) {
        const r = await submitImg2VideoGeneration({
          modelId: modelId.value,
          prompt: prompt.value,
          ratio: ratio.value,
          resolution: resolution.value,
          duration: duration.value,
          inputAssetIds: refs.map((a) => a.id),
          userId,
        })
        taskId = r.taskId
      } else {
        const r = await submitVideoGeneration({
          modelId: modelId.value,
          prompt: prompt.value,
          ratio: ratio.value,
          resolution: resolution.value,
          duration: duration.value,
          userId,
        })
        taskId = r.taskId
      }
      if (taskId) {
        const done = await pollTaskUntilDone(taskId, userId, 'video')
        const first = done.images?.[0] as { url: string; asset_id?: number } | undefined
        if (first?.asset_id) asset = { id: first.asset_id, url: first.url, isVideo: true }
      }
    }

    if (asset) {
      emit('generated', asset)
      ElMessage.success('生成完成')
      emit('close')
    } else {
      ElMessage.error('生成结果无效')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    generating.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="ngd">
      <div v-if="visible" class="ngd-overlay" @click="!generating && emit('close')">
        <div class="ngd-modal" @click.stop>
          <div class="ngd-header">
            <span class="ngd-title">{{ mode === 'image' ? '图片生成' : '视频生成' }}</span>
            <button class="ngd-close" :disabled="generating" @click="emit('close')">✕</button>
          </div>

          <div class="ngd-body">
            <!-- 模型 -->
            <div class="ngd-field">
              <label class="ngd-label">模型</label>
              <select v-model="modelId" class="ngd-select">
                <option v-for="m in models" :key="m.id" :value="m.id">{{ m.description || m.name }}</option>
              </select>
            </div>

            <!-- 提示词 -->
            <div class="ngd-field">
              <label class="ngd-label">提示词</label>
              <textarea v-model="prompt" class="ngd-textarea" rows="3" placeholder="描述你想生成的内容" />
            </div>

            <!-- 图片参数 -->
            <template v-if="mode === 'image'">
              <div class="ngd-field">
                <label class="ngd-label">比例</label>
                <div class="ngd-chips">
                  <button v-for="r in RATIOS" :key="r" class="ngd-chip" :class="{ active: aspectRatio === r }" @click="aspectRatio = r">{{ r }}</button>
                </div>
              </div>
              <div class="ngd-field">
                <label class="ngd-label">清晰度</label>
                <div class="ngd-chips">
                  <button v-for="q in QUALITIES" :key="q" class="ngd-chip" :class="{ active: quality === q }" @click="quality = q">{{ q }}</button>
                </div>
              </div>
              <div class="ngd-field">
                <label class="ngd-label">数量</label>
                <div class="ngd-stepper">
                  <button class="ngd-step" @click="batchSize = Math.max(1, batchSize - 1)">-</button>
                  <span class="ngd-step-val">{{ batchSize }}</span>
                  <button class="ngd-step" @click="batchSize = Math.min(4, batchSize + 1)">+</button>
                </div>
              </div>
            </template>

            <!-- 视频参数 -->
            <template v-else>
              <div class="ngd-field">
                <label class="ngd-label">比例</label>
                <div class="ngd-chips">
                  <button v-for="r in VIDEO_RATIOS" :key="r" class="ngd-chip" :class="{ active: ratio === r }" @click="ratio = r">{{ r }}</button>
                </div>
              </div>
              <div class="ngd-field">
                <label class="ngd-label">分辨率</label>
                <div class="ngd-chips">
                  <button v-for="r in RESOLUTIONS" :key="r" class="ngd-chip" :class="{ active: resolution === r }" @click="resolution = r">{{ r }}</button>
                </div>
              </div>
              <div class="ngd-field">
                <label class="ngd-label">时长(秒)</label>
                <div class="ngd-stepper">
                  <button class="ngd-step" @click="duration = Math.max(1, duration - 1)">-</button>
                  <span class="ngd-step-val">{{ duration }}</span>
                  <button class="ngd-step" @click="duration = Math.min(60, duration + 1)">+</button>
                </div>
              </div>
            </template>

            <!-- 参考图（来自上一面板的图片资产） -->
            <div v-if="refCandidates.length > 0" class="ngd-field">
              <label class="ngd-label">参考图（选自上一面板，可多选）</label>
              <div class="ngd-refs">
                <div
                  v-for="a in refCandidates"
                  :key="a.id"
                  class="ngd-ref"
                  :class="{ selected: selectedRefIds.includes(a.id) }"
                  @click="toggleRef(a.id)"
                >
                  <img :src="a.url" class="ngd-ref-img" />
                  <span v-if="selectedRefIds.includes(a.id)" class="ngd-ref-check">✓</span>
                </div>
              </div>
            </div>
          </div>

          <div class="ngd-footer">
            <button class="ngd-btn cancel" :disabled="generating" @click="emit('close')">取消</button>
            <button class="ngd-btn confirm" :disabled="generating" @click="handleGenerate">
              {{ generating ? '生成中...' : '开始生成' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ngd-overlay {
  position: fixed;
  inset: 0;
  z-index: 3500;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.ngd-modal {
  width: 92%;
  max-width: 480px;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  background: rgba(25, 25, 30, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  box-shadow: 0 25px 80px rgba(0, 0, 0, 0.6);
  overflow: hidden;
}
.ngd-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}
.ngd-title { font-size: 15px; color: rgba(255, 255, 255, 0.9); font-weight: 500; }
.ngd-close {
  width: 28px; height: 28px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: transparent;
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  transition: all 0.2s;
}
.ngd-close:hover:not(:disabled) { background: rgba(255, 255, 255, 0.08); color: #fff; }
.ngd-close:disabled { opacity: 0.4; cursor: not-allowed; }

.ngd-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ngd-body::-webkit-scrollbar { width: 5px; }
.ngd-body::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.16); border-radius: 3px; }

.ngd-field { display: flex; flex-direction: column; gap: 8px; }
.ngd-label { font-size: 12px; color: rgba(255, 255, 255, 0.5); }
.ngd-select,
.ngd-textarea {
  width: 100%;
  padding: 9px 12px;
  border-radius: 9px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.9);
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}
.ngd-textarea { resize: vertical; font-family: inherit; line-height: 1.5; }
.ngd-select option { background: #1a1a20; }

.ngd-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ngd-chip {
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.ngd-chip:hover { color: rgba(255, 255, 255, 0.9); }
.ngd-chip.active {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.28);
  color: #fff;
}

.ngd-stepper { display: flex; align-items: center; gap: 10px; }
.ngd-step {
  width: 30px; height: 30px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.8);
  font-size: 16px;
  cursor: pointer;
}
.ngd-step:hover { background: rgba(255, 255, 255, 0.1); }
.ngd-step-val { min-width: 28px; text-align: center; color: #fff; font-size: 14px; }

.ngd-refs { display: flex; flex-wrap: wrap; gap: 8px; }
.ngd-ref {
  position: relative;
  width: 60px; height: 60px;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid transparent;
  cursor: pointer;
  transition: border-color 0.2s;
}
.ngd-ref.selected { border-color: var(--color-primary, #a6e7e2); }
.ngd-ref-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ngd-ref-check {
  position: absolute;
  top: 2px; right: 2px;
  width: 18px; height: 18px;
  border-radius: 50%;
  background: var(--color-primary, #a6e7e2);
  color: #000;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ngd-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}
.ngd-btn {
  padding: 9px 20px;
  border-radius: 9px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.2s;
}
.ngd-btn.cancel {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.6);
}
.ngd-btn.cancel:hover:not(:disabled) { background: rgba(255, 255, 255, 0.08); color: #fff; }
.ngd-btn.confirm {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.28);
  color: #fff;
}
.ngd-btn.confirm:hover:not(:disabled) { background: rgba(255, 255, 255, 0.2); }
.ngd-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.ngd-enter-active, .ngd-leave-active { transition: opacity 0.25s; }
.ngd-enter-from, .ngd-leave-to { opacity: 0; }
.ngd-enter-active .ngd-modal { animation: ngd-pop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); }
@keyframes ngd-pop {
  0% { opacity: 0; transform: scale(0.9) translateY(20px); }
  100% { opacity: 1; transform: scale(1) translateY(0); }
}
</style>
