<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { ElInput, ElSelect, ElOption, ElSlider, ElInputNumber } from 'element-plus'
import { Refresh, UploadFilled, Close, Setting } from '@element-plus/icons-vue'
import { ElImageViewer } from 'element-plus'
import AssetPicker from '../components/AssetPicker.vue'
import RecordCard from '../components/RecordCard.vue'
import ImageEditor from '../components/ImageEditor.vue'
import { getModels, getKSamplerInfo, submitPrompt, uploadImage, type PromptParams } from '../api/comfyui'
import { useComfyWebSocket } from '../composables/useComfyWebSocket'
import { getApiModels, type ApiModel } from '../api/apiService'
import { useGenerationHistory } from '../composables/useGenerationHistory'
import { useTaskPolling } from '../composables/useTaskPolling'
import { useAtMention } from '../composables/useAtMention'
import { useImageSizeControl } from '../composables/useImageSizeControl'
import { useRecordEditor } from '../composables/useRecordEditor'
import { submitImageGeneration, type InputImage } from '../services/imageGenerationService'
import { getCurrentUserId } from '../utils/user'
import { generateUUID } from '../utils/uuid'

const { clientId, progress, generating, imageUrl, connect, startGeneration } = useComfyWebSocket()

// ── 图片预览 ──────────────────────────────────────────────
const showImageViewer = ref(false)
const previewImageUrl = ref('')
function previewImage(url: string) {
  previewImageUrl.value = url
  showImageViewer.value = true
}

// ── 生成记录类型 ──────────────────────────────────────────
interface GenerationRecord {
  id: string
  createdAt: number
  prompt: string
  inputPreviews: string[]
  inputAssetUrls?: Array<{ url: string; type: string }>
  modelName: string
  mode: 'api' | 'local'
  status: 'generating' | 'done' | 'error'
  progress: number
  images: string[]
  errorMsg?: string
  taskId?: string
  isImg2Img?: boolean
  dbId?: number
  inputAssetIds?: number[]
  modelId?: number
}

// ── 历史记录 ──────────────────────────────────────────────
const {
  records, saveRecords, searchQuery, expandedInputs, filteredRecords,
  toggleInputExpand, deleteRecord, clearAll, loadFromDb, markStaleRecords,
} = useGenerationHistory<GenerationRecord>(
  'generation_history',
  'img',
  (r) => ({ images: r.images.filter((img: string) => img.startsWith('http') || img.startsWith('/')) }),
)

// ── 任务轮询 ──────────────────────────────────────────────
const { resumeTaskPolling } = useTaskPolling<GenerationRecord>(
  () => records.value as GenerationRecord[],
  saveRecords,
)

function pollImage(record: GenerationRecord, userId?: number) {
  return resumeTaskPolling(record, userId, (rec, result) => {
    rec.images = result.images.map((i: any) => i.url).filter(Boolean) as string[]
  })
}

// ── 模型 ──────────────────────────────────────────────────
const apiModels = ref<ApiModel[]>([])
const apiModel = ref('')
const models = ref<string[]>([])
const samplers = ref<string[]>([])
const schedulers = ref<string[]>([])
const modelSource = ref<'local' | 'api'>('local')

// ── 表单参数 ──────────────────────────────────────────────
const activeTab = ref<'txt2img' | 'img2img'>('txt2img')
const isImg2Img = computed(() => activeTab.value === 'img2img')
const showAdvanced = ref(false)
const errorMsg = ref('')
const justSubmitted = ref(false)

const form = ref<PromptParams>({
  ckpt_name: '',
  positive_prompt: '',
  negative_prompt: '',
  width: 512,
  height: 512,
  seed: Math.floor(Math.random() * 2 ** 32),
  steps: 20,
  cfg: 8,
  sampler_name: 'dpmpp_2m',
  scheduler: 'karras',
  denoise: 1,
  batch_size: 1,
})

// ── 尺寸控制 ──────────────────────────────────────────────
const { ratios, resolutions, activeRatio, activeResolution, ratioOpen, sizeCustomized,
  setRatio, setResolution, startStep, stopStep } =
  useImageSizeControl(
    () => ({ width: form.value.width, height: form.value.height }),
    (w, h) => { form.value.width = w; form.value.height = h },
  )

// ── 输入图片 ──────────────────────────────────────────────
const inputImages = ref<InputImage[]>([])
const showAssetPicker = ref(false)
const selectedAssetLocation = ref('')

function addLocalImage(file: File) {
  if (inputImages.value.length >= 4) return
  inputImages.value.push({ file, preview: URL.createObjectURL(file), assetLocation: '' })
}

function handleAssetSelect(assets: Array<{ id: number; location: string; asset_type?: string }>) {
  if (activeTab.value === 'img2img') {
    const maxImages = modelSource.value === 'api' ? 4 : 1
    for (const asset of assets) {
      if (inputImages.value.length >= maxImages) break
      const filename = asset.location.replace(/\\/g, '/').split('/').pop()!
      inputImages.value.push({
        file: null,
        preview: `/api/view?filename=${encodeURIComponent(filename)}&type=output`,
        assetLocation: asset.location,
      })
    }
  } else {
    if (assets.length > 0) selectedAssetLocation.value = assets[0].location
  }
}

// ── @mention ──────────────────────────────────────────────
const promptInputRef = ref<InstanceType<typeof ElInput> | null>(null)
const { atMentionActive, atMentionIndex, onPromptKeyup, onPromptKeydown, insertMention } =
  useAtMention(
    () => form.value.positive_prompt,
    (v) => { form.value.positive_prompt = v },
    () => inputImages.value.map(img => ({ url: img.preview, type: 'image' as const })),
    promptInputRef,
  )

// ── 图片编辑器（输入图） ──────────────────────────────────
const showEditor = ref(false)
const editingIndex = ref(-1)
const assetPickerTargetIndex = ref(-1)

function openEditor(idx: number) {
  editingIndex.value = idx
  showEditor.value = true
}

function onEditorConfirm(file: File) {
  const idx = editingIndex.value
  if (idx >= 0 && idx < inputImages.value.length) {
    inputImages.value[idx] = { file, preview: URL.createObjectURL(file), assetLocation: '' }
  }
  showEditor.value = false
}

// ── 历史记录编辑面板 ──────────────────────────────────────
const inlineEditorRef = ref<InstanceType<typeof ImageEditor> | null>(null)
const {
  showRecordEditor, editingRecordId, recordEditorPrompt, recordEditorImages,
  recordEditorEditedPreview, recordEditorEditingSrc, showRecordImageEditor,
  openEditor: openRecordEditor, onImageEditorConfirm: onRecordImageEditorConfirm,
  onImageEditorCancel: onRecordImageEditorCancel, closeEditor: closeRecordEditor, getEditedFile,
} = useRecordEditor(inlineEditorRef)

function handleRecordEdit(id: string) {
  const rec = (records.value as GenerationRecord[]).find(r => r.id === id)
  if (!rec || rec.status !== 'done') return
  openRecordEditor(rec)
}

async function generateFromEdit() {
  if (!apiModel.value) { errorMsg.value = '请先选择 API 模型'; return }
  closeRecordEditor()

  const editedFile = await getEditedFile()
  const src = editedFile ? URL.createObjectURL(editedFile) : recordEditorImages.value[0]
  if (!src) return

  const record: GenerationRecord = {
    id: generateUUID(), createdAt: Date.now(),
    prompt: recordEditorPrompt.value, inputPreviews: [src],
    modelName: apiModel.value, modelId: Number(apiModel.value) || undefined,
    mode: 'api', status: 'generating', progress: 0, images: [], isImg2Img: true,
  }
  records.value.unshift(record)
  saveRecords()

  const inputImg: InputImage = editedFile
    ? { file: editedFile, preview: src, assetLocation: '' }
    : { file: null, preview: src, assetLocation: '' }

  runApiGeneration(record.id, true, [inputImg])
}

// ── 核心生成逻辑 ──────────────────────────────────────────
async function runApiGeneration(recordId: string, img2img: boolean, snapshotImages: InputImage[]) {
  const getRecord = () => (records.value as GenerationRecord[]).find(r => r.id === recordId)
  const rec = getRecord()
  if (!rec) return

  try {
    const userId = getCurrentUserId()
    const result = await submitImageGeneration({
      modelId: rec.modelId,
      prompt: rec.prompt,
      width: form.value.width,
      height: form.value.height,
      batchSize: form.value.batch_size,
      img2img,
      inputImages: snapshotImages,
      userId: userId ?? undefined,
    })

    if (result.taskId) {
      rec.taskId = result.taskId
      saveRecords()
      pollImage(rec, userId ?? undefined).catch(console.error)
    } else {
      rec.images = result.images || []
      rec.status = 'done'
      saveRecords()
    }
  } catch (e: any) {
    const r = getRecord()
    if (r) { r.status = 'error'; r.errorMsg = e.message }
    saveRecords()
  }
}

async function retryRecord(record: GenerationRecord) {
  if (record.dbId) {
    const userId = getCurrentUserId()
    if (userId) {
      const { useHistoryDb } = await import('../composables/useHistoryDb')
      await useHistoryDb().remove(record.dbId, userId)
    }
  }

  const newRecord: GenerationRecord = {
    id: generateUUID(), createdAt: Date.now(),
    mode: record.mode, prompt: record.prompt, modelName: record.modelName,
    status: 'generating', inputPreviews: record.inputPreviews,
    progress: 0, images: [], isImg2Img: record.isImg2Img,
  }
  records.value = [newRecord, ...(records.value as GenerationRecord[]).filter(r => r.id !== record.id)] as any
  saveRecords()

  if (record.mode !== 'api') {
    newRecord.status = 'error'; newRecord.errorMsg = '本地模式不支持重试'; saveRecords(); return
  }
  const model = apiModels.value.find(m => m.id === record.modelName)
  if (!model) {
    newRecord.status = 'error'; newRecord.errorMsg = '找不到对应的模型'; saveRecords(); return
  }

  if (record.isImg2Img) {
    const snapshotImages: InputImage[] = (record.inputPreviews || []).map(url => {
      const match = url.match(/\/api\/view\?filename=([^&]+)/)
      const assetLocation = match ? decodeURIComponent(match[1]) : ''
      return { file: null, preview: url, assetLocation }
    }).filter(img => img.assetLocation)

    if (snapshotImages.length === 0) {
      newRecord.status = 'error'
      newRecord.errorMsg = '无法重试：本地上传的图片不支持重试，请重新上传'
      saveRecords(); return
    }
    runApiGeneration(newRecord.id, true, snapshotImages)
  } else {
    runApiGeneration(newRecord.id, false, [])
  }
}

// ── 主生成入口 ────────────────────────────────────────────
async function handleGenerate() {
  errorMsg.value = ''
  const modelName = modelSource.value === 'api'
    ? (apiModels.value.find(m => m.id === apiModel.value)?.name || apiModel.value)
    : form.value.ckpt_name
  const inputPreviews = inputImages.value.map(img => img.preview)

  if (modelSource.value === 'api') {
    if (!apiModel.value) { errorMsg.value = '请先在模型管理中添加 API 模型'; return }
    if (isImg2Img.value && inputImages.value.length === 0) {
      errorMsg.value = '请先上传或选择参考图片'; return
    }
    const record: GenerationRecord = {
      id: generateUUID(), createdAt: Date.now(),
      prompt: form.value.positive_prompt, inputPreviews, modelName,
      modelId: Number(apiModel.value) || undefined,
      mode: 'api', status: 'generating', progress: 0, images: [],
      isImg2Img: isImg2Img.value,
    }
    records.value.unshift(record)
    saveRecords()
    justSubmitted.value = true
    setTimeout(() => justSubmitted.value = false, 1000)
    runApiGeneration(record.id, isImg2Img.value, [...inputImages.value])
    return
  }

  // 本地 ComfyUI 模式
  if (!form.value.ckpt_name) { errorMsg.value = '请先选择模型'; return }
  const record: GenerationRecord = {
    id: generateUUID(), createdAt: Date.now(),
    prompt: form.value.positive_prompt, inputPreviews, modelName,
    mode: 'local', status: 'generating', progress: 0, images: [],
  }
  records.value.unshift(record)
  saveRecords()

  try {
    if (isImg2Img.value) {
      const firstImg = inputImages.value[0]
      if (!firstImg) {
        record.status = 'error'; record.errorMsg = '请先上传或选择参考图片'; saveRecords(); return
      }
      if (firstImg.file) {
        form.value.input_image = await uploadImage(firstImg.file)
      } else if (firstImg.assetLocation) {
        form.value.input_image = firstImg.assetLocation
      } else {
        record.status = 'error'; record.errorMsg = '请先上传或选择参考图片'; saveRecords(); return
      }
    } else {
      form.value.input_image = undefined
    }
    const res = await submitPrompt(form.value, clientId)
    startGeneration(res.prompt_id)
  } catch {
    errorMsg.value = '提交失败，请检查 ComfyUI 后端'
    const rec = (records.value as GenerationRecord[]).find(r => r.mode === 'local' && r.status === 'generating')
    if (rec) { rec.status = 'error'; rec.errorMsg = '提交失败'; saveRecords() }
    generating.value = false
  }
}

function downloadImage(url: string, filename?: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename || url.split('/').pop() || 'image.png'
  a.click()
}

// ── 本地模式 WebSocket 进度 ───────────────────────────────
watch(progress, (val) => {
  const rec = (records.value as GenerationRecord[]).find(r => r.mode === 'local' && r.status === 'generating')
  if (rec) rec.progress = val
})

watch(imageUrl, (url) => {
  if (!url) return
  const rec = (records.value as GenerationRecord[]).find(r => r.mode === 'local' && r.status === 'generating')
  if (rec) { rec.images = [url]; rec.status = 'done'; saveRecords() }
})

watch(generating, (val) => {
  if (!val) {
    const rec = (records.value as GenerationRecord[]).find(r => r.mode === 'local' && r.status === 'generating')
    if (rec && rec.images.length === 0) { rec.status = 'error'; rec.errorMsg = '生成超时或失败'; saveRecords() }
  }
})

watch(isImg2Img, (val) => { form.value.denoise = val ? 0.75 : 1 })

// ── 初始化 ────────────────────────────────────────────────
onMounted(async () => {
  connect()

  try {
    const [modelList, ksInfo] = await Promise.all([getModels(), getKSamplerInfo()])
    models.value = modelList
    samplers.value = ksInfo.samplers
    schedulers.value = ksInfo.schedulers
    if (modelList.length > 0) form.value.ckpt_name = modelList[0]
    else errorMsg.value = '未找到任何 checkpoint 模型'
  } catch {
    errorMsg.value = '无法连接 ComfyUI 后端（默认 127.0.0.1:8188）'
  }

  try {
    apiModels.value = await getApiModels('image')
    if (apiModels.value.length > 0) apiModel.value = apiModels.value[0].id
  } catch {}

  const userId = await loadFromDb((r) => ({
    id: String(r.id),
    dbId: r.id,
    createdAt: 0,
    prompt: r.prompt || '',
    inputPreviews: [],
    inputAssetUrls: r.input_asset_urls || [],
    modelName: r.model_name || '',
    mode: 'api' as const,
    status: (r.status === 'error' ? 'error' : 'done') as 'done' | 'error',
    progress: 100,
    images: r.output_urls.map((o: any) => o.url),
    inputAssetIds: r.input_asset_ids,
    errorMsg: r.status === 'error' ? (r.message || '生成失败') : undefined,
  }), (r) => r.status !== 'pending' && r.status !== 'processing')

  const pending = markStaleRecords('local')
  for (const rec of pending) {
    pollImage(rec as GenerationRecord, userId).catch(console.error)
  }

  ;(records.value as GenerationRecord[]).filter(r => r.mode === 'local' && r.status === 'generating').forEach(r => {
    r.status = 'error'; r.errorMsg = '页面刷新，生成中断'
  })
  saveRecords()
})
</script>


<template>
  <div class="page">
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <div class="layout">
      <!-- ── LEFT PANEL（编辑模式时隐藏） ── -->
      <aside class="left-panel" v-show="!showRecordEditor">

        <!-- tab bar -->
        <div class="tab-bar">
          <button class="tab-btn" :class="{ active: activeTab === 'txt2img' }" @click="activeTab = 'txt2img'">文生图</button>
          <button class="tab-btn" :class="{ active: activeTab === 'img2img' }" @click="activeTab = 'img2img'">图生图</button>
        </div>

        <div class="panel-body">
          <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

          <!-- model source toggle — 最顶部 -->
          <div class="row-item">
            <span class="row-label">调用方式</span>
            <div class="source-toggle">
              <button :class="{ active: modelSource === 'local' }" @click="modelSource = 'local'">本地模型</button>
              <button :class="{ active: modelSource === 'api' }" @click="modelSource = 'api'">API 调用</button>
            </div>
          </div>

          <!-- local model select -->
          <div v-if="modelSource === 'local'" class="row-item">
            <span class="row-label">模型</span>
            <ElSelect v-model="form.ckpt_name" placeholder="选择模型" filterable class="row-select">
              <ElOption v-for="m in models" :key="m" :label="m" :value="m" />
            </ElSelect>
          </div>
          <div v-else-if="apiModels.length > 0" class="row-item">
            <span class="row-label">API 模型</span>
            <ElSelect v-model="apiModel" placeholder="选择模型" class="row-select">
              <ElOption v-for="m in apiModels" :key="m.id" :label="m.name" :value="m.id" />
            </ElSelect>
          </div>
          <div v-else class="api-tip">
            <span>请先在</span>
            <router-link to="/models" class="api-tip-link">模型管理</router-link>
            <span>中添加 API 模型</span>
          </div>

          <div class="divider" />

          <!-- img2img upload -->
          <template v-if="activeTab === 'img2img'">
            <div class="section-label">参考图片
              <span v-if="modelSource === 'local' && inputImages.length > 1" class="local-tip">本地模式仅使用图1</span>
            </div>

            <!-- 已上传的图片列表 -->
            <div v-if="inputImages.length > 0" class="multi-preview-wrap">
              <div v-for="(img, idx) in inputImages" :key="idx" class="preview-item">
                <span class="img-label">图{{ idx + 1 }}</span>
                <img :src="img.preview" class="preview-img" />
                <button class="edit-btn" @click="openEditor(idx)" title="编辑图片">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19l7-7-3-3-7 7v3h3z"/><path d="M18 13l1.5-1.5a2.12 2.12 0 0 0-3-3L15 10"/></svg>
                </button>
                <button class="clear-btn" @click="inputImages.splice(idx, 1)"><el-icon><Close /></el-icon></button>
              </div>
            </div>

            <!-- 添加图片按钮（最多4张）-->
            <div v-if="inputImages.length < 4" class="upload-actions">
              <button class="asset-btn" @click="assetPickerTargetIndex = -1; showAssetPicker = true">
                <span>从资产选择</span>
              </button>
              <label class="local-upload-btn">
                <input type="file" accept="image/*" @change="(e) => {
                  const file = (e.target as HTMLInputElement).files?.[0]
                  if (file) addLocalImage(file);
                  (e.target as HTMLInputElement).value = ''
                }" hidden />
                <el-icon><UploadFilled /></el-icon>
                <span>本地上传</span>
              </label>
            </div>
          </template>

          <!-- prompt -->
          <div class="section-label">{{ activeTab === 'txt2img' ? '描述你想生成的内容' : '描述生成方向' }}</div>
          <div class="prompt-wrap">
            <ElInput
              ref="promptInputRef"
              v-model="form.positive_prompt"
              type="textarea" :rows="4"
              :placeholder="activeTab === 'txt2img' ? '输入提示词，描述画面内容、风格、光线...（@ 选参考图）' : '描述想要生成的内容方向...（@ 选参考图）'"
              class="prompt-input"
              @keyup="onPromptKeyup"
              @keydown="onPromptKeydown"
              @blur="atMentionActive = false"
            />
            <!-- @ 提及下拉：从已上传图片中选择 -->
            <div v-if="atMentionActive && inputImages.length > 0" class="mention-dropdown">
              <div
                v-for="(img, idx) in inputImages"
                :key="idx"
                class="mention-item"
                :class="{ active: atMentionIndex === idx }"
                @mousedown.prevent="insertMention(idx)"
              >
                <img :src="img.preview" class="mention-thumb" />
                <span>@图{{ idx + 1 }}</span>
              </div>
            </div>
          </div>
          <!-- 反向提示词：仅本地模式显示 -->
          <ElInput
            v-if="modelSource === 'local'"
            v-model="form.negative_prompt"
            type="textarea" :rows="2"
            placeholder="反向提示词（不想出现的内容）"
            class="prompt-input neg"
          />
          
          <div class="divider" />

          <!-- resolution -->
          <div class="row-item">
            <span class="row-label">清晰度</span>
            <div class="source-toggle">
              <button
                v-for="r in resolutions" :key="r.label"
                :class="{ active: !sizeCustomized && activeResolution.label === r.label }"
                @click="setResolution(r)"
              >{{ r.label }}</button>
            </div>
          </div>

          <!-- ratio -->
          <div class="row-item">
            <span class="row-label">比例</span>
            <div class="ratio-select">
              <div class="ratio-current" :class="{ dimmed: sizeCustomized }" @click="ratioOpen = !ratioOpen">
                <span class="ratio-icon">{{ activeRatio.icon }}</span>
                <span class="ratio-label-text">{{ sizeCustomized ? '自定义' : activeRatio.label }}</span>
                <span class="ratio-arrow" :class="{ open: ratioOpen }">›</span>
              </div>
              <div class="ratio-dropdown" v-show="ratioOpen">
                <div
                  v-for="r in ratios" :key="r.label"
                  class="ratio-option"
                  :class="{ active: !sizeCustomized && activeRatio.label === r.label }"
                  @click="setRatio(r); ratioOpen = false"
                >
                  <span class="ratio-icon">{{ r.icon }}</span>
                  <span>{{ r.label }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- size preview -->
          <div class="size-preview">{{ form.width }} × {{ form.height }}</div>

          <!-- batch size -->
          <div class="row-item">
            <span class="row-label">数量</span>
            <div class="source-toggle">
              <button
                v-for="n in [1,2,3,4]" :key="n"
                :class="{ active: form.batch_size === n }"
                @click="form.batch_size = n"
              >{{ n }}</button>
            </div>
          </div>

          <!-- denoise — 图生图直接显示（仅本地模式） -->
          <div v-if="isImg2Img && modelSource === 'local'" class="field">
            <div class="row-item" style="margin-bottom:4px">
              <span class="row-label">降噪强度</span>
              <span class="row-label">{{ form.denoise }}</span>
            </div>
            <ElSlider v-model="form.denoise" :min="0" :max="1" :step="0.01" />
          </div>

          <!-- advanced toggle：仅本地模式显示 -->
          <button v-if="modelSource === 'local'" class="advanced-toggle" @click="showAdvanced = !showAdvanced">
            <el-icon><Setting /></el-icon>
            高级参数
            <span class="toggle-arrow" :class="{ open: showAdvanced }">›</span>
          </button>

          <div v-if="modelSource === 'local'" class="advanced-panel" :class="{ visible: showAdvanced }">
            <div class="two-col">
              <div class="field">
                <span class="row-label">宽度</span>
                <div class="stepper">
                  <button class="stepper-btn" @mousedown="startStep('width',-8)" @mouseup="stopStep" @mouseleave="stopStep">−</button>
                  <input class="stepper-input" type="number" v-model.number="form.width" :min="16" :max="2048" :step="8" @input="sizeCustomized = true" />
                  <button class="stepper-btn" @mousedown="startStep('width',8)" @mouseup="stopStep" @mouseleave="stopStep">+</button>
                </div>
              </div>
              <div class="field">
                <span class="row-label">高度</span>
                <div class="stepper">
                  <button class="stepper-btn" @mousedown="startStep('height',-8)" @mouseup="stopStep" @mouseleave="stopStep">−</button>
                  <input class="stepper-input" type="number" v-model.number="form.height" :min="16" :max="2048" :step="8" @input="sizeCustomized = true" />
                  <button class="stepper-btn" @mousedown="startStep('height',8)" @mouseup="stopStep" @mouseleave="stopStep">+</button>
                </div>
              </div>
            </div>

            <div class="field">
              <span class="row-label">种子</span>
              <div class="seed-row">
                <ElInputNumber v-model="form.seed" :min="0" :max="Number.MAX_SAFE_INTEGER" controls-position="right" class="seed-input" />
                <button class="icon-btn" @click="form.seed = Math.floor(Math.random() * 2 ** 32)">
                  <el-icon><Refresh /></el-icon>
                </button>
              </div>
            </div>

            <div class="two-col">
              <div class="field">
                <span class="row-label">步数 {{ form.steps }}</span>
                <ElSlider v-model="form.steps" :min="1" :max="150" />
              </div>
              <div class="field">
                <span class="row-label">CFG {{ form.cfg }}</span>
                <ElSlider v-model="form.cfg" :min="0" :max="30" :step="0.5" />
              </div>
            </div>

            <div class="two-col">
              <div class="field">
                <span class="row-label">采样器</span>
                <ElSelect v-model="form.sampler_name" filterable class="full-width">
                  <ElOption v-for="s in samplers" :key="s" :label="s" :value="s" />
                </ElSelect>
              </div>
              <div class="field">
                <span class="row-label">调度器</span>
                <ElSelect v-model="form.scheduler" filterable class="full-width">
                  <ElOption v-for="s in schedulers" :key="s" :label="s" :value="s" />
                </ElSelect>
              </div>
            </div>
          </div>

          <!-- generate -->
          <button class="generate-btn" :class="{ loading: generating, submitted: justSubmitted }" :disabled="generating || justSubmitted" @click="handleGenerate">
            <span class="btn-glow" />
            <span class="btn-label">{{ justSubmitted ? '已提交 ✓' : generating ? '生成中...' : '开始生成' }}</span>
          </button>
        </div>
      </aside>

      <!-- ── RIGHT: MESSAGE STREAM ── -->
      <main class="right-panel">
        <!-- 编辑模式：编辑器 + 提示词侧边栏 -->
        <template v-if="showRecordEditor">
          <!-- 中间：图片编辑器 -->
          <div class="editor-area">
            <ImageEditor
              v-if="recordEditorEditingSrc"
              ref="inlineEditorRef"
              :image-src="recordEditorEditedPreview || recordEditorEditingSrc"
              :visible="true"
              :inline="true"
              @confirm="onRecordImageEditorConfirm"
              @cancel="showRecordEditor = false"
            />
          </div>
          <!-- 右侧：提示词 + 生成按钮 -->
          <div class="edit-sidebar">
            <div class="record-edit-header">
              <span class="record-edit-title">继续生图</span>
              <button class="record-edit-close" @click="showRecordEditor = false">×</button>
            </div>
            <div class="record-edit-label">提示词</div>
            <textarea
              v-model="recordEditorPrompt"
              class="record-edit-textarea"
              rows="4"
              placeholder="修改提示词..."
            />
            <button class="generate-btn record-edit-generate-btn" @click="generateFromEdit">
              <span class="btn-glow" />
              <span class="btn-label">继续生图</span>
            </button>
          </div>
        </template>

        <!-- 历史记录（始终保留 DOM 防止滚动重置） -->
        <div class="history-col" v-show="!showRecordEditor">
            <div v-if="filteredRecords.length === 0 && records.length === 0" class="empty-wrap">
              <div class="empty-orb" />
              <p class="empty-text">等待生成</p>
            </div>
            <div v-else class="stream">
              <!-- 搜索框 -->
              <div class="stream-header">
                <span class="stream-title">历史记录 ({{ filteredRecords.length }})</span>
                <input v-model="searchQuery" class="search-input" placeholder="搜索提示词..." />
              </div>

              <div v-for="rec in filteredRecords" :key="rec.id" class="record-row" :class="{ 'editing': showRecordEditor && editingRecordId === rec.id }">
                <!-- 左侧输入图 -->
                <div class="record-input-col">
                  <template v-if="(rec.inputAssetUrls && rec.inputAssetUrls.length) || (rec.inputPreviews && rec.inputPreviews.length)">
                    <button class="input-toggle-btn" @click="toggleInputExpand(rec.id)">
                      参考图
                      <span class="input-toggle-arrow" :class="{ open: expandedInputs.has(rec.id) }">›</span>
                    </button>
                    <template v-if="expandedInputs.has(rec.id)">
                      <template v-if="rec.inputAssetUrls && rec.inputAssetUrls.length">
                        <template v-for="(a, i) in rec.inputAssetUrls" :key="'a' + i">
                          <video v-if="a.type === 'video'" :src="a.url" class="input-panel-thumb" controls />
                          <img v-else :src="a.url" class="input-panel-thumb" @click="previewImage(a.url)" />
                        </template>
                      </template>
                      <template v-else-if="rec.inputPreviews && rec.inputPreviews.length">
                        <img v-for="(p, i) in rec.inputPreviews" :key="i" :src="p" class="input-panel-thumb" @click="previewImage(p)" />
                      </template>
                    </template>
                  </template>
                </div>
                <!-- 右侧卡片 -->
                <RecordCard class="record-card-flex" :record="rec" @delete="deleteRecord" @retry="(r) => retryRecord(r as any)" @edit="handleRecordEdit">
                  <template #prompt>
                    <p class="card-prompt">{{ rec.prompt }}</p>
                  </template>
                  <template #progress>
                    <div v-if="rec.mode === 'local' && rec.progress > 0" class="progress-wrap">
                      <div class="progress-bar" :style="{ width: rec.progress + '%' }" />
                      <span class="progress-text">{{ rec.progress }}%</span>
                    </div>
                    <span v-else class="loading-text">生成中...</span>
                  </template>
                  <template #result>
                    <div class="card-images">
                      <div v-for="(src, i) in rec.images" :key="i" class="card-image-wrap">
                        <img :src="src" class="card-image" @click="previewImage(src)" />
                        <button class="download-btn" @click="downloadImage(src)" title="下载">
                          <span>⬇</span>
                        </button>
                      </div>
                    </div>
                  </template>
                </RecordCard>
              </div>
            </div>
          </div>
      </main>
    </div>

    <!-- Asset Picker Dialog -->
    <AssetPicker
      v-model:visible="showAssetPicker"
      :max-select="activeTab === 'img2img' && modelSource === 'api' ? 4 - inputImages.length : 1"
      @select="handleAssetSelect"
    />

    <!-- Image Viewer -->
    <el-image-viewer
      v-if="showImageViewer"
      :url-list="[previewImageUrl]"
      @close="showImageViewer = false"
      :hide-on-click-modal="true"
    />

    <!-- Image Editor（输入图编辑） -->
    <ImageEditor
      v-if="showEditor && editingIndex >= 0 && inputImages[editingIndex]"
      :image-src="inputImages[editingIndex].preview"
      :visible="showEditor"
      @confirm="onEditorConfirm"
      @cancel="showEditor = false"
    />

    <!-- 历史记录图片编辑器（已内联到侧边栏，此处无需渲染） -->
  </div>
</template>

<style scoped>
@import '../styles/generation-page.css';

/* ── 图片页专属样式 ── */

.local-tip {
  font-size: 10px;
  color: rgba(167,139,250,0.7);
  letter-spacing: 0;
}

.prompt-input.neg :deep(.el-textarea__inner) {
  background: rgba(248,113,113,0.04) !important;
  border-color: rgba(248,113,113,0.1) !important;
}

.size-preview {
  font-size: 11px;
  color: rgba(255,255,255,0.25);
  text-align: right;
  letter-spacing: 1px;
  margin-top: -4px;
}

/* ratio dropdown */
.ratio-select {
  position: relative;
  flex: 1;
  max-width: 160px;
}

.ratio-current {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s;
  user-select: none;
}
.ratio-current:hover { border-color: rgba(108,99,255,0.4); }
.ratio-current.dimmed { opacity: 0.45; }

.ratio-icon { font-size: 13px; line-height: 1; flex-shrink: 0; }
.ratio-label-text { font-size: 12px; color: rgba(255,255,255,0.8); flex: 1; }
.ratio-arrow {
  font-size: 14px; color: rgba(255,255,255,0.3);
  transition: transform 0.2s; display: inline-block;
}
.ratio-arrow.open { transform: rotate(90deg); }

.ratio-dropdown {
  position: absolute;
  top: calc(100% + 6px); left: 0; right: 0;
  background: rgba(14,14,26,0.97);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px; overflow: hidden;
  z-index: 50; backdrop-filter: blur(16px);
}

.ratio-option {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; font-size: 12px;
  color: rgba(255,255,255,0.6); cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.ratio-option:hover { background: rgba(108,99,255,0.15); color: rgba(255,255,255,0.9); }
.ratio-option.active { color: #a78bfa; background: rgba(108,99,255,0.1); }

/* advanced toggle */
.advanced-toggle {
  display: flex; align-items: center; gap: 6px;
  background: none; border: none;
  color: rgba(255,255,255,0.35); font-size: 12px;
  cursor: pointer; padding: 4px 0; letter-spacing: 0.5px;
  transition: color 0.2s;
}
.advanced-toggle:hover { color: rgba(255,255,255,0.65); }

.toggle-arrow {
  margin-left: auto; font-size: 16px;
  transition: transform 0.3s ease; display: inline-block;
}
.toggle-arrow.open { transform: rotate(90deg); }

.advanced-panel {
  max-height: 0; overflow: hidden; opacity: 0;
  transition: max-height 0.4s ease, opacity 0.3s ease;
  display: flex; flex-direction: column; gap: 12px;
}
.advanced-panel.visible { max-height: 900px; opacity: 1; }

.field { display: flex; flex-direction: column; gap: 6px; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

/* stepper */
.stepper {
  display: flex; align-items: center;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px; overflow: hidden; height: 34px;
  transition: border-color 0.2s;
}
.stepper:hover { border-color: rgba(108,99,255,0.35); }

.stepper-btn {
  width: 30px; height: 100%;
  background: none; border: none;
  color: rgba(255,255,255,0.45); font-size: 15px; cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.stepper-btn:hover { background: rgba(108,99,255,0.2); color: #fff; }

.stepper-input {
  flex: 1; height: 100%;
  background: transparent; border: none; outline: none;
  color: rgba(255,255,255,0.9); font-size: 13px; text-align: center;
  -moz-appearance: textfield;
}
.stepper-input::-webkit-outer-spin-button,
.stepper-input::-webkit-inner-spin-button { -webkit-appearance: none; }

.seed-row { display: flex; gap: 8px; }
.seed-input { flex: 1; }

.icon-btn {
  width: 34px; height: 34px; border-radius: 8px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.5); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.2s, color 0.2s; flex-shrink: 0;
}
.icon-btn:hover { background: rgba(108,99,255,0.2); color: #fff; }

.full-width { width: 100%; }

/* 多图预览 */
.multi-preview-wrap { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.preview-item {
  position: relative; width: calc(50% - 4px);
  border-radius: 10px; overflow: hidden;
  border: 1px solid rgba(255,255,255,0.08);
}
.preview-item .preview-img { max-height: 120px; }
.img-label {
  position: absolute; top: 6px; left: 6px;
  background: rgba(0,0,0,0.65); color: #a78bfa;
  font-size: 11px; padding: 2px 7px; border-radius: 6px;
  font-weight: 600; letter-spacing: 1px;
}

/* 图片结果 */
.card-images { display: flex; flex-wrap: wrap; gap: 12px; }
.card-image-wrap {
  position: relative;
  max-width: calc(50% - 6px); flex-shrink: 0;
}
.card-images:has(.card-image-wrap:only-child) .card-image-wrap { max-width: 480px; }
.card-image {
  width: 100%; max-height: 400px;
  border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,0.4);
  display: block; object-fit: contain; cursor: pointer;
}
.card-image-wrap:hover .download-btn { opacity: 1; }

/* 进度 */
.loading-text { font-size: 12px; color: rgba(255,255,255,0.35); }

.record-row.editing {
  outline: 1px solid rgba(108,99,255,0.3);
  border-radius: 16px;
}
</style>

