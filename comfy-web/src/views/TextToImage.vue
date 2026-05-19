<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { ElInput, ElSelect, ElOption, ElSlider, ElInputNumber } from 'element-plus'
import { Refresh, UploadFilled, Close, Setting } from '@element-plus/icons-vue'
import { ElImageViewer } from 'element-plus'
import AssetPicker from '../components/AssetPicker.vue'
import RecordCard from '../components/RecordCard.vue'
import { getModels, getKSamplerInfo, submitPrompt, uploadImage, type PromptParams } from '../api/comfyui'
import { useComfyWebSocket } from '../composables/useComfyWebSocket'
import { getApiModels, apiGenerate, pollTaskUntilDone, resolveImageSrc, uploadInputImage, type ApiModel } from '../api/apiService'
import { useTaskHistory } from '../composables/useTaskHistory'
import { useHistoryDb } from '../composables/useHistoryDb'
import { getCurrentUserId } from '../utils/user'
import { generateUUID } from '../utils/uuid'

const { clientId, progress, generating, imageUrl, connect, startGeneration } = useComfyWebSocket()

// 图片预览
const showImageViewer = ref(false)
const previewImageUrl = ref('')

function previewImage(url: string) {
  previewImageUrl.value = url
  showImageViewer.value = true
}

// ── 生成记录 ──────────────────────────────────────────────
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
  dbId?: number        // 数据库 history 表的主键，用于删除/同步
  inputAssetIds?: number[]
  modelId?: number
}

const HISTORY_KEY = 'generation_history'
const MAX_RECORDS = 50

const { records, saveRecords, clearAll: clearAllLocal, formatTime, deleteRecord: deleteRecordLocal } = useTaskHistory<GenerationRecord>(
  HISTORY_KEY,
  MAX_RECORDS,
  (r) => ({ images: r.images.filter(img => img.startsWith('http') || img.startsWith('/')) }),
)

const historyDb = useHistoryDb()

const searchQuery = ref('')
const filteredRecords = computed(() => {
  if (!searchQuery.value.trim()) return records.value as GenerationRecord[]
  const q = searchQuery.value.trim().toLowerCase()
  return (records.value as GenerationRecord[]).filter(r => r.prompt.toLowerCase().includes(q))
})

// 包装删除：同时删除 DB 记录
async function deleteRecord(id: string) {
  const rec = (records.value as GenerationRecord[]).find(r => r.id === id)
  if (rec?.dbId) {
    const userId = getCurrentUserId()
    if (userId) await historyDb.remove(rec.dbId, userId)
  }
  await deleteRecordLocal(id)
}

// 包装清空：同时清空 DB
async function clearAll() {
  const userId = getCurrentUserId()
  if (userId) await historyDb.clear(userId)
  clearAllLocal()
}

async function retryRecord(record: GenerationRecord) {
  // 软删除旧记录
  if (record.dbId) {
    const userId = getCurrentUserId()
    if (userId) await historyDb.remove(record.dbId, userId)
  }
  const newRecord: GenerationRecord = {
    id: generateUUID(),
    createdAt: Date.now(),
    mode: record.mode,
    prompt: record.prompt,
    modelName: record.modelName,
    status: 'generating',
    inputPreviews: record.inputPreviews,
    progress: 0,
    images: [],
    isImg2Img: record.isImg2Img,
  }
  records.value.unshift(newRecord)
  records.value = records.value.filter(r => r.id !== record.id) as any
  saveRecords()

  if (record.mode === 'api') {
    const model = apiModels.value.find(m => m.id === record.modelName)
    if (!model) {
      newRecord.status = 'error'
      newRecord.errorMsg = '找不到对应的模型'
      saveRecords()
      return
    }

    if (record.isImg2Img) {
      // 从存储的预览 URL 中还原资产路径（仅支持资产图片，本地上传的 blob URL 已失效）
      const snapshotImages: InputImage[] = (record.inputPreviews || []).map(url => {
        const match = url.match(/\/api\/view\?filename=([^&]+)/)
        const assetLocation = match ? decodeURIComponent(match[1]) : ''
        return { file: null, preview: url, assetLocation }
      }).filter(img => img.assetLocation)

      if (snapshotImages.length === 0) {
        newRecord.status = 'error'
        newRecord.errorMsg = '无法重试：本地上传的图片不支持重试，请重新上传'
        saveRecords()
        return
      }

      runApiGeneration(newRecord.id, true, snapshotImages)
    } else {
      const userId = getCurrentUserId()
      try {
        const result = await apiGenerate({
          model: model.id,
          prompt: record.prompt,
          width: form.value.width,
          height: form.value.height,
          n: form.value.batch_size,
          user_id: userId,
        })

        if ('taskId' in result) {
          newRecord.taskId = result.taskId
          saveRecords()
          resumeTaskPolling(newRecord, userId).catch(err => {
            console.error('Polling error:', err)
          })
        }
      } catch (e: any) {
        newRecord.status = 'error'
        newRecord.errorMsg = e.message
        saveRecords()
      }
    }
  } else {
    newRecord.status = 'error'
    newRecord.errorMsg = '本地模式不支持重试'
    saveRecords()
  }
}




function downloadImage(url: string, filename?: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename || url.split('/').pop() || 'image.png'
  a.click()
}

// API 模式状态（保留用于按钮禁用判断）
const apiModels = ref<ApiModel[]>([])
const apiModel = ref('')

// tabs: txt2img | img2img
const activeTab = ref<'txt2img' | 'img2img'>('txt2img')

// model source: local | api
const modelSource = ref<'local' | 'api'>('local')

const models = ref<string[]>([])
const samplers = ref<string[]>([])
const schedulers = ref<string[]>([])
const showAdvanced = ref(false)

// 多图上传（img2img）
interface InputImage {
  file: File | null
  preview: string
  assetLocation: string
}
const inputImages = ref<InputImage[]>([])
const showAssetPicker = ref(false)
const assetPickerTargetIndex = ref(-1)  // 当前要替换的图片索引，-1 表示新增
const promptInputRef = ref<InstanceType<typeof ElInput> | null>(null)
const atMentionActive = ref(false)  // 是否由 @ 触发的资产选择
const atMentionStartIdx = ref(-1)   // @ 在 prompt 中的位置

// 兼容旧的单图逻辑（本地 ComfyUI 模式）
const inputImageFile = ref<File | null>(null)
const inputImagePreview = ref('')
const selectedAssetLocation = ref('')

const isImg2Img = computed(() => activeTab.value === 'img2img')

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

const errorMsg = ref('')

const ratios = [
  { label: '1:1',  w: 1,  h: 1,  icon: '⬜' },
  { label: '16:9', w: 16, h: 9,  icon: '▬' },
  { label: '9:16', w: 9,  h: 16, icon: '▮' },
  { label: '4:3',  w: 4,  h: 3,  icon: '▭' },
  { label: '3:4',  w: 3,  h: 4,  icon: '▯' },
]
const activeRatio = ref(ratios[0])

const resolutions = [
  { label: '512',  base: 512 },
  { label: '768',  base: 768 },
  { label: '1024', base: 1024 },
  { label: '1080p', base: 1920 },
]
const activeResolution = ref(resolutions[0])
const ratioOpen = ref(false)
const sizeCustomized = ref(false)

function applyRatioAndRes() {
  const { w, h } = activeRatio.value
  const base = activeResolution.value.base
  if (w >= h) {
    form.value.width  = Math.round(base / 8) * 8
    form.value.height = Math.round(base * h / w / 8) * 8
  } else {
    form.value.height = Math.round(base / 8) * 8
    form.value.width  = Math.round(base * w / h / 8) * 8
  }
  sizeCustomized.value = false
}

function setRatio(r: typeof ratios[0]) {
  activeRatio.value = r
  applyRatioAndRes()
}
function setResolution(r: typeof resolutions[0]) {
  activeResolution.value = r
  applyRatioAndRes()
}

let stepTimer: ReturnType<typeof setTimeout> | null = null
let stepInterval: ReturnType<typeof setInterval> | null = null

function startStep(field: 'width' | 'height', delta: number) {
  applyStep(field, delta)
  stepTimer = setTimeout(() => {
    stepInterval = setInterval(() => applyStep(field, delta), 80)
  }, 500)
}
function applyStep(field: 'width' | 'height', delta: number) {
  form.value[field] = Math.min(2048, Math.max(16, form.value[field] + delta))
  sizeCustomized.value = true
}
function stopStep() {
  if (stepTimer) { clearTimeout(stepTimer); stepTimer = null }
  if (stepInterval) { clearInterval(stepInterval); stepInterval = null }
}

watch(isImg2Img, (val) => { form.value.denoise = val ? 0.75 : 1 })

const atMentionIndex = ref(-1) // 键盘高亮项

function onPromptKeyup(e: KeyboardEvent) {
  if (e.key === '@') {
    if (inputImages.value.length === 0) return
    const textarea = promptInputRef.value?.textarea
    if (!textarea) return
    atMentionStartIdx.value = textarea.selectionStart - 1
    atMentionActive.value = true
    atMentionIndex.value = -1
  } else if (e.key === 'Escape') {
    atMentionActive.value = false
  }
}

function onPromptKeydown(e: KeyboardEvent | Event) {
  if (!(e instanceof KeyboardEvent)) return
  if (!atMentionActive.value) return
  const count = inputImages.value.length
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    atMentionIndex.value = (atMentionIndex.value + 1) % count
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    atMentionIndex.value = (atMentionIndex.value - 1 + count) % count
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (atMentionIndex.value >= 0) insertMention(atMentionIndex.value)
  }
}

function insertMention(idx: number) {
  const textarea = promptInputRef.value?.textarea
  if (!textarea) return
  const label = `@图${idx + 1}`
  const start = atMentionStartIdx.value
  const before = form.value.positive_prompt.slice(0, start)
  const after = form.value.positive_prompt.slice(start + 1) // 跳过 @
  form.value.positive_prompt = `${before}${label} ${after}`
  atMentionActive.value = false
  atMentionIndex.value = -1
  textarea.focus()
}

onMounted(async () => {
  connect()
  // 加载本地模型
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
  // 加载 API 模型
  try {
    apiModels.value = await getApiModels('image')
    if (apiModels.value.length > 0) apiModel.value = apiModels.value[0].id
  } catch {}

  const userId = getCurrentUserId()

  // 从数据库加载历史，合并到 records（以 DB 为准，保留本地进行中的任务）
  if (userId) {
    const dbRecords = await historyDb.load(userId, 'img')
    const localPending = (records.value as GenerationRecord[]).filter(r => r.status === 'generating')
    // 本地已完成记录若 DB 中存在对应条目则跳过（避免重复）
    const fromDb: GenerationRecord[] = dbRecords.map(r => ({
      id: String(r.id),
      dbId: r.id,
      createdAt: 0,
      prompt: r.prompt || '',
      inputPreviews: [],
      inputAssetUrls: r.input_asset_urls || [],
      modelName: r.model_name || '',
      mode: 'api' as const,
      status: 'done' as const,
      progress: 100,
      images: r.output_urls.map(o => o.url),
      inputAssetIds: r.input_asset_ids,
    }))
    records.value = [...localPending, ...fromDb] as any
    saveRecords()
  }

  // 恢复刷新前未完成的 API 任务
  const pending = (records.value as GenerationRecord[]).filter(r => r.mode === 'api' && r.status === 'generating' && r.taskId)
  for (const rec of pending) {
    resumeTaskPolling(rec, userId)
  }
  // API 任务没有 taskId 的（直接返回结果但 base64 被过滤掉了）→ 标记失败
  ;(records.value as GenerationRecord[]).filter(r => r.mode === 'api' && r.status === 'generating' && !r.taskId).forEach(r => {
    r.status = 'error'
    r.errorMsg = '页面刷新，结果已丢失（base64 图片无法持久化）'
  })
  // 本地模式刷新后无法恢复，标记为失败
  ;(records.value as GenerationRecord[]).filter(r => r.mode === 'local' && r.status === 'generating').forEach(r => {
    r.status = 'error'
    r.errorMsg = '页面刷新，生成中断'
  })
  saveRecords()
})

function handleImageChange(file: any) {
  inputImageFile.value = file.raw
  inputImagePreview.value = URL.createObjectURL(file.raw)
  selectedAssetLocation.value = ''
}
function clearInputImage() {
  inputImageFile.value = null
  inputImagePreview.value = ''
  selectedAssetLocation.value = ''
}

function openAssetPicker() {
  showAssetPicker.value = true
}

function addLocalImage(file: File) {
  if (inputImages.value.length >= 4) return
  inputImages.value.push({ file, preview: URL.createObjectURL(file), assetLocation: '' })
}

function handleAssetSelect(assets: Array<{ id: number; location: string; asset_type?: string }>) {
  if (activeTab.value === 'img2img') {
    const maxImages = modelSource.value === 'api' ? 4 : 1
    for (const asset of assets) {
      if (inputImages.value.length >= maxImages) break
      inputImages.value.push({
        file: null,
        preview: `/api/view?filename=${encodeURIComponent(asset.location)}&type=output`,
        assetLocation: asset.location,
      })
    }
  } else {
    // txt2img 模式，只取第一个
    if (assets.length > 0) {
      selectedAssetLocation.value = assets[0].location
    }
  }
}

async function runApiGeneration(
  recordId: string,
  img2img: boolean,
  snapshotImages: InputImage[],
) {
  const getRecord = () => records.value.find(r => r.id === recordId)
  try {
    let input_asset_ids: number[] | undefined
    if (img2img) {
      if (snapshotImages.length === 0) {
        const rec = getRecord(); if (rec) { rec.status = 'error'; rec.errorMsg = '请先上传或选择参考图片' }
        saveRecords()
        return
      }
      const userId = getCurrentUserId() ?? 1
      const ids: number[] = []
      for (const img of snapshotImages) {
        if (img.file) {
          const uploaded = await uploadInputImage(img.file, userId)
          ids.push(uploaded.id)
        } else if (img.assetLocation) {
          const imgRes = await fetch(`/api/view?filename=${encodeURIComponent(img.assetLocation)}&type=output`)
          const blob = await imgRes.blob()
          const file = new File([blob], img.assetLocation, { type: blob.type })
          const uploaded = await uploadInputImage(file, userId)
          ids.push(uploaded.id)
        }
      }
      input_asset_ids = ids
    }
    const rec = getRecord()
    // 把 input_asset_ids 存到 record，轮询完成后持久化时能拿到
    if (rec && input_asset_ids) rec.inputAssetIds = input_asset_ids
    const userId = getCurrentUserId()
    const submitted = await apiGenerate({
      model: rec ? rec.modelName : apiModel.value,
      prompt: rec ? rec.prompt : form.value.positive_prompt,
      width: form.value.width,
      height: form.value.height,
      n: form.value.batch_size,
      input_asset_ids,
      user_id: userId,
    })

    if (submitted.taskId) {
      const r = getRecord(); if (r) { r.taskId = submitted.taskId }
      saveRecords()
      const r2 = getRecord(); if (r2) await resumeTaskPolling(r2, userId)
    } else {
      const r = getRecord()
      if (r) {
        r.images = submitted.images.map(resolveImageSrc).filter(Boolean)
        r.status = 'done'
      }
      saveRecords()
    }
  } catch (e: any) {
    const r = getRecord()
    if (r) { r.status = 'error'; r.errorMsg = (e as any).message }
    saveRecords()
  }
}

async function resumeTaskPolling(record: GenerationRecord, userId?: number) {
  if (!record.taskId) return
  try {
    // 先查一次状态，避免重复轮询已完成的任务
    const checkUrl = userId ? `/api/api-proxy/task/${record.taskId}?user_id=${userId}` : `/api/api-proxy/task/${record.taskId}`
    const checkRes = await fetch(checkUrl)
    if (checkRes.ok) {
      const checkData = await checkRes.json()
      if (checkData.status === 'completed' && checkData.result) {
        const rec = records.value.find(r => r.id === record.id)
        if (rec) {
          rec.images = checkData.result.map((item: any) => item.url).filter(Boolean)
          rec.status = 'done'
          if (checkData.history_id) rec.dbId = checkData.history_id
          saveRecords()
        }
        return
      } else if (checkData.status === 'failed') {
        const rec = records.value.find(r => r.id === record.id)
        if (rec) {
          rec.status = 'error'
          rec.errorMsg = checkData.error?.error_message || '任务失败'
          saveRecords()
        }
        return
      }
    }
    // 任务还在进行中，开始轮询
    const result = await pollTaskUntilDone(record.taskId, userId)
    const rec = records.value.find(r => r.id === record.id)
    if (rec) {
      rec.images = result.images.map(resolveImageSrc).filter(Boolean)
      rec.status = 'done'
      if ((result as any).historyId) rec.dbId = (result as any).historyId
    }
  } catch (e: any) {
    const rec = records.value.find(r => r.id === record.id)
    if (rec) {
      rec.status = 'error'
      rec.errorMsg = (e as any).message
    }
  } finally {
    saveRecords()
  }
}

async function handleGenerate() {
  errorMsg.value = ''

  const modelName = modelSource.value === 'api' ? apiModel.value : form.value.ckpt_name
  const inputPreviews = inputImages.value.map(img => img.preview)

  // ── API 调用模式 ──
  if (modelSource.value === 'api') {
    if (!apiModel.value) { errorMsg.value = '请先在模型管理中添加 API 模型'; return }

    const record: GenerationRecord = {
      id: generateUUID(),
      createdAt: Date.now(),
      prompt: form.value.positive_prompt,
      inputPreviews,
      modelName,
      modelId: Number(apiModel.value) || undefined,
      mode: 'api',
      status: 'generating',
      progress: 0,
      images: [],
      isImg2Img: isImg2Img.value,
    }
    records.value.unshift(record)
    saveRecords()

    // 快照当前图片列表，fire-and-forget
    runApiGeneration(record.id, isImg2Img.value, [...inputImages.value])
    return
  }

  // ── 本地 ComfyUI 模式 ──
  if (!form.value.ckpt_name) { errorMsg.value = '请先选择模型'; return }

  const record: GenerationRecord = {
    id: generateUUID(),
    createdAt: Date.now(),
    prompt: form.value.positive_prompt,
    inputPreviews,
    modelName,
    mode: 'local',
    status: 'generating',
    progress: 0,
    images: [],
  }
  records.value.unshift(record)
  saveRecords()

  try {
    if (isImg2Img.value) {
      const firstImg = inputImages.value[0]
      if (!firstImg) {
        errorMsg.value = '请先上传或选择参考图片'
        record.status = 'error'
        record.errorMsg = '请先上传或选择参考图片'
        saveRecords()
        return
      }
      if (firstImg.file) {
        form.value.input_image = await uploadImage(firstImg.file)
      } else if (firstImg.assetLocation) {
        form.value.input_image = firstImg.assetLocation
      } else {
        errorMsg.value = '请先上传或选择参考图片'
        record.status = 'error'
        record.errorMsg = '请先上传或选择参考图片'
        saveRecords()
        return
      }
    } else {
      form.value.input_image = undefined
    }
    const res = await submitPrompt(form.value, clientId)
    startGeneration(res.prompt_id)
  } catch {
    errorMsg.value = '提交失败，请检查 ComfyUI 后端'
    const rec = records.value.find(r => r.mode === 'local' && r.status === 'generating')
    if (rec) { rec.status = 'error'; rec.errorMsg = '提交失败，请检查 ComfyUI 后端'; saveRecords() }
    generating.value = false
  }
}

// 本地模式：WebSocket 进度更新到当前 record
watch(progress, (val) => {
  const rec = records.value.find(r => r.mode === 'local' && r.status === 'generating')
  if (rec) rec.progress = val
})

watch(imageUrl, async (url) => {
  if (!url) return
  const rec = records.value.find(r => r.mode === 'local' && r.status === 'generating')
  if (rec) {
    rec.images = [url]
    rec.status = 'done'
    saveRecords()
  }
})

watch(generating, (val) => {
  if (!val) {
    const rec = records.value.find(r => r.mode === 'local' && r.status === 'generating')
    if (rec && rec.images.length === 0) {
      rec.status = 'error'
      rec.errorMsg = '生成超时或失败'
      saveRecords()
    }
  }
})
</script>

<template>
  <div class="page">
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <div class="layout">
      <!-- ── LEFT PANEL ── -->
      <aside class="left-panel">

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
          <button class="generate-btn" :class="{ loading: generating }" :disabled="generating" @click="handleGenerate">
            <span class="btn-glow" />
            <span class="btn-label">{{ generating ? '生成中...' : '开始生成' }}</span>
          </button>
        </div>
      </aside>

      <!-- ── RIGHT: MESSAGE STREAM ── -->
      <main class="right-panel">
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

          <div v-for="rec in filteredRecords" :key="rec.id">
            <RecordCard :record="rec" @delete="deleteRecord" @retry="(r) => retryRecord(r as any)">
              <template #meta>
                <div v-if="(rec.inputAssetUrls && rec.inputAssetUrls.length) || (rec.inputPreviews && rec.inputPreviews.length)" class="card-previews">
                  <template v-if="rec.inputAssetUrls && rec.inputAssetUrls.length">
                    <template v-for="(a, i) in rec.inputAssetUrls" :key="'a' + i">
                      <video v-if="a.type === 'video'" :src="a.url" class="card-preview-img" />
                      <img v-else :src="a.url" class="card-preview-img" />
                    </template>
                  </template>
                  <img v-else v-for="(p, i) in rec.inputPreviews" :key="i" :src="p" class="card-preview-img" />
                </div>
              </template>
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
  </div>
</template>

<style scoped>
/* ── Page shell ── */
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

/* ── Two-column layout ── */
.layout {
  position: relative;
  z-index: 1;
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* ── Left panel ── */
.left-panel {
  width: 340px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(255,255,255,0.06);
  background: rgba(255,255,255,0.02);
  backdrop-filter: blur(16px);
  overflow-y: auto;
}

/* tab bar */
.tab-bar {
  display: flex;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
  margin: 20px 20px 0;
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255,255,255,0.03);
}

.tab-btn {
  flex: 1;
  height: 40px;
  background: none;
  border: none;
  color: rgba(255,255,255,0.35);
  font-size: 13px;
  letter-spacing: 1px;
  cursor: pointer;
  position: relative;
  transition: color 0.2s, background 0.2s;
  border-radius: 0;
}
.tab-btn.active {
  color: rgba(255,255,255,0.9);
  background: rgba(108,99,255,0.2);
}

/* panel body */
.panel-body {
  padding: 20px 20px 32px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-label {
  font-size: 11px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 1px;
  margin-bottom: -4px;
  display: flex; align-items: center; gap: 8px;
}
.local-tip {
  font-size: 10px;
  color: rgba(167,139,250,0.7);
  letter-spacing: 0;
}

/* prompt inputs */
.prompt-wrap { position: relative; width: 100%; }
.prompt-input { width: 100%; }
.mention-dropdown {
  position: absolute;
  z-index: 100;
  background: #1e1e2e;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 8px;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 140px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
}
.mention-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #e2e8f0;
}
.mention-item:hover, .mention-item.active { background: rgba(255,255,255,0.08); }
.mention-thumb {
  width: 32px;
  height: 32px;
  object-fit: cover;
  border-radius: 4px;
}
.prompt-input.neg :deep(.el-textarea__inner) {
  background: rgba(248,113,113,0.04) !important;
  border-color: rgba(248,113,113,0.1) !important;
}

/* divider */
.divider {
  height: 1px;
  background: rgba(255,255,255,0.06);
  margin: 4px 0;
}

/* row items */
.row-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.row-label {
  font-size: 12px;
  color: rgba(255,255,255,0.4);
  white-space: nowrap;
  flex-shrink: 0;
}

.row-select { flex: 1; }

/* source toggle */
.source-toggle {
  display: flex;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  overflow: hidden;
}
.source-toggle button {
  padding: 5px 14px;
  background: none;
  border: none;
  color: rgba(255,255,255,0.35);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}
.source-toggle button.active {
  background: rgba(108,99,255,0.25);
  color: rgba(255,255,255,0.9);
}

/* api tip */
.api-tip {
  font-size: 12px;
  color: rgba(167,139,250,0.5);
  padding: 10px 14px;
  border: 1px dashed rgba(108,99,255,0.2);
  border-radius: 10px;
  text-align: center;
  letter-spacing: 1px;
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

.ratio-icon {
  font-size: 13px;
  line-height: 1;
  flex-shrink: 0;
}

.ratio-label-text {
  font-size: 12px;
  color: rgba(255,255,255,0.8);
  flex: 1;
}

.ratio-arrow {
  font-size: 14px;
  color: rgba(255,255,255,0.3);
  transition: transform 0.2s;
  display: inline-block;
}
.ratio-arrow.open { transform: rotate(90deg); }

.ratio-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0; right: 0;
  background: rgba(14,14,26,0.97);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px;
  overflow: hidden;
  z-index: 50;
  backdrop-filter: blur(16px);
}

.ratio-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  font-size: 12px;
  color: rgba(255,255,255,0.6);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.ratio-option:hover { background: rgba(108,99,255,0.15); color: rgba(255,255,255,0.9); }
.ratio-option.active { color: #a78bfa; background: rgba(108,99,255,0.1); }

/* advanced toggle */
.advanced-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: rgba(255,255,255,0.35);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 0;
  letter-spacing: 0.5px;
  transition: color 0.2s;
}
.advanced-toggle:hover { color: rgba(255,255,255,0.65); }

.toggle-arrow {
  margin-left: auto;
  font-size: 16px;
  transition: transform 0.3s ease;
  display: inline-block;
}
.toggle-arrow.open { transform: rotate(90deg); }

/* advanced panel */
.advanced-panel {
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  transition: max-height 0.4s ease, opacity 0.3s ease;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.advanced-panel.visible { max-height: 900px; opacity: 1; }

/* field */
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* two-col */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

/* stepper */
.stepper {
  display: flex;
  align-items: center;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  overflow: hidden;
  height: 34px;
  transition: border-color 0.2s;
}
.stepper:hover { border-color: rgba(108,99,255,0.35); }

.stepper-btn {
  width: 30px; height: 100%;
  background: none; border: none;
  color: rgba(255,255,255,0.45);
  font-size: 15px; cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.stepper-btn:hover { background: rgba(108,99,255,0.2); color: #fff; }

.stepper-input {
  flex: 1; height: 100%;
  background: transparent; border: none; outline: none;
  color: rgba(255,255,255,0.9);
  font-size: 13px; text-align: center;
  -moz-appearance: textfield;
}
.stepper-input::-webkit-outer-spin-button,
.stepper-input::-webkit-inner-spin-button { -webkit-appearance: none; }

/* seed */
.seed-row { display: flex; gap: 8px; }
.seed-input { flex: 1; }

.icon-btn {
  width: 34px; height: 34px;
  border-radius: 8px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.5);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.2s, color 0.2s;
  flex-shrink: 0;
}
.icon-btn:hover { background: rgba(108,99,255,0.2); color: #fff; }

/* upload actions */
.upload-actions {
  display: flex;
  gap: 10px;
}

.asset-btn, .local-upload-btn {
  flex: 1;
  height: 80px;
  border-radius: 10px;
  border: 1px dashed rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.03);
  color: rgba(255,255,255,0.5);
  font-size: 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.3s;
}
.asset-btn:hover, .local-upload-btn:hover {
  border-color: rgba(108,99,255,0.45);
  background: rgba(108,99,255,0.04);
  color: rgba(255,255,255,0.8);
}

.preview-wrap {
  position: relative; width: 100%;
  border-radius: 10px; overflow: hidden;
  border: 1px solid rgba(255,255,255,0.08);
}
.preview-img {
  width: 100%; max-height: 160px;
  object-fit: contain; display: block;
  background: rgba(0,0,0,0.3);
}
.clear-btn {
  position: absolute; top: 6px; right: 6px;
  width: 24px; height: 24px; border-radius: 50%;
  background: rgba(0,0,0,0.6); border: none;
  color: white; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; transition: background 0.2s;
}
.clear-btn:hover { background: rgba(220,50,50,0.7); }

.multi-preview-wrap {
  display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px;
}
.preview-item {
  position: relative; width: calc(50% - 4px);
  border-radius: 10px; overflow: hidden;
  border: 1px solid rgba(255,255,255,0.08);
}
.preview-item .preview-img {
  max-height: 120px;
}
.img-label {
  position: absolute; top: 6px; left: 6px;
  background: rgba(0,0,0,0.65); color: #a78bfa;
  font-size: 11px; padding: 2px 7px; border-radius: 6px;
  font-weight: 600; letter-spacing: 1px;
}

/* generate button */
.generate-btn {
  position: relative;
  width: 100%; height: 46px;
  margin-top: 8px;
  border-radius: 12px; border: none;
  cursor: pointer; overflow: hidden;
  background: linear-gradient(135deg, #6c63ff, #a78bfa, #6c63ff);
  background-size: 200% auto;
  color: #fff; font-size: 14px;
  font-weight: 600; letter-spacing: 2px;
  transition: opacity 0.2s, transform 0.15s;
  animation: shimmer 3s linear infinite;
}
.generate-btn:hover:not(:disabled) { transform: translateY(-1px); opacity: 0.9; }
.generate-btn:active:not(:disabled) { transform: translateY(0); }
.generate-btn:disabled { opacity: 0.45; cursor: not-allowed; animation: none; }
.generate-btn.loading { animation: breathe 2s ease-in-out infinite; }

.btn-glow {
  position: absolute; inset: 0;
  border-radius: inherit; background: inherit;
  filter: blur(12px); opacity: 0;
  transition: opacity 0.3s; z-index: -1;
}
.generate-btn:not(:disabled):hover .btn-glow { opacity: 0.5; }
.btn-label { position: relative; z-index: 1; }

.error-msg {
  color: #f87171; font-size: 12px;
  padding: 8px 12px;
  background: rgba(248,113,113,0.07);
  border-radius: 8px;
  border: 1px solid rgba(248,113,113,0.18);
}

.full-width { width: 100%; }

/* ── Right panel ── */
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 32px 40px;
  overflow-y: auto;
}

/* message stream */
.stream {
  width: 100%;
  max-width: 720px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.stream-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.stream-title {
  font-size: 13px;
  color: rgba(255,255,255,0.5);
  letter-spacing: 0.5px;
}

.search-input {
  flex: 1;
  max-width: 200px;
  padding: 5px 10px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 6px;
  color: rgba(255,255,255,0.8);
  font-size: 12px;
  outline: none;
  transition: border-color 0.2s;
}
.search-input::placeholder { color: rgba(255,255,255,0.25); }
.search-input:focus { border-color: rgba(108,99,255,0.5); }

.card-previews {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.card-preview-img {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.08);
}

.card-model-name {
  font-size: 11px;
  color: rgba(108,99,255,0.8);
  margin-top: 4px;
}

.card-prompt {
  font-size: 13px;
  color: rgba(255,255,255,0.7);
  line-height: 1.6;
  margin: 0;
  word-break: break-all;
}

/* generating state */
.progress-wrap {
  flex: 1;
  position: relative;
  height: 4px;
  background: rgba(255,255,255,0.08);
  border-radius: 4px;
  overflow: visible;
}
.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #6c63ff, #a78bfa);
  border-radius: 4px;
  transition: width 0.3s ease;
}
.progress-text {
  position: absolute;
  right: 0;
  top: -18px;
  font-size: 11px;
  color: rgba(255,255,255,0.4);
}

/* done: image grid */
.card-images {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.card-image-wrap {
  position: relative;
  max-width: calc(50% - 6px);
  flex-shrink: 0;
}
.card-images:has(.card-image-wrap:only-child) .card-image-wrap {
  max-width: 100%;
}

.card-image {
  width: 100%;
  max-height: 480px;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.4);
  display: block;
  object-fit: contain;
  cursor: pointer;
}

.download-btn {
  position: absolute;
  bottom: 12px;
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
.card-image-wrap:hover .download-btn {
  opacity: 1;
}
.download-btn:hover {
  background: rgba(108,99,255,0.9);
  transform: scale(1.1);
}

/* error */
/* empty */
.empty-wrap {
  display: flex; flex-direction: column;
  align-items: center; gap: 14px;
  margin: auto;
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

@media (max-width: 900px) {
  .layout { flex-direction: column; height: auto; }
  .left-panel { width: 100%; border-right: none; border-bottom: 1px solid rgba(255,255,255,0.06); }
  .right-panel { padding: 24px 20px; }
}
</style>
