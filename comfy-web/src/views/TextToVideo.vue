<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElInput, ElSelect, ElOption, ElImageViewer } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import AssetPicker from '../components/AssetPicker.vue'
import RecordCard from '../components/RecordCard.vue'
import ImageEditor from '../components/ImageEditor.vue'
import { apiVideoGenerate, apiImg2VideoGenerate, uploadInputImage, getApiModels, type ApiModel } from '../api/apiService'
import { useTaskHistory } from '../composables/useTaskHistory'
import { useHistoryDb } from '../composables/useHistoryDb'
import { getCurrentUserId } from '../utils/user'
import { generateUUID } from '../utils/uuid'

// ── 生成记录 ──────────────────────────────────────────────
interface VideoRecord {
  id: string
  createdAt: number
  prompt: string
  modelName: string
  ratio: string
  resolution: string
  duration: number
  status: 'generating' | 'done' | 'error'
  videoUrl?: string
  errorMsg?: string
  taskId?: string
  mode: 'txt2video' | 'img2video'
  inputAssetIds?: number[]
  inputAssetUrls?: Array<{ url: string; type: string }>
  dbId?: number
  modelId?: number
}

const HISTORY_KEY = 'video_generation_history'
const MAX_RECORDS = 50

const { records, saveRecords, clearAll: clearAllLocal, deleteRecord: deleteRecordLocal } = useTaskHistory<VideoRecord>(
  HISTORY_KEY,
  MAX_RECORDS,
)

const historyDb = useHistoryDb()

const searchQuery = ref('')
const filteredRecords = computed(() => {
  if (!searchQuery.value.trim()) return records.value as VideoRecord[]
  const q = searchQuery.value.trim().toLowerCase()
  return (records.value as VideoRecord[]).filter(r => r.prompt.toLowerCase().includes(q))
})

async function deleteRecord(id: string) {
  const rec = (records.value as VideoRecord[]).find(r => r.id === id)
  if (rec?.dbId) {
    const userId = getCurrentUserId()
    if (userId) await historyDb.remove(rec.dbId, userId)
  }
  await deleteRecordLocal(id)
}

async function clearAll() {
  const userId = getCurrentUserId()
  if (userId) await historyDb.clear(userId)
  clearAllLocal()
}

async function retryRecord(record: VideoRecord) {
  // 软删除旧记录
  if (record.dbId) {
    const userId = getCurrentUserId()
    if (userId) await historyDb.remove(record.dbId, userId)
  }
  // 创建新记录，复用原来的参数
  const newRecord: VideoRecord = {
    id: generateUUID(),
    createdAt: Date.now(),
    prompt: record.prompt,
    modelName: record.modelName,
    ratio: record.ratio,
    resolution: record.resolution,
    duration: record.duration,
    status: 'generating',
    mode: record.mode,
    inputAssetIds: record.inputAssetIds,
  }
  records.value.unshift(newRecord)
  records.value = records.value.filter(r => r.id !== record.id) as any
  saveRecords()

  // 重新提交任务（需要找到对应的 model id）
  const model = apiModels.value.find(m => m.id === record.modelName || m.name === record.modelName)
  if (!model) {
    newRecord.status = 'error'
    newRecord.errorMsg = '找不到对应的模型'
    saveRecords()
    return
  }

  const userId = getCurrentUserId()

  try {
    let taskId: string

    // 根据模式调用不同的接口
    if (record.mode === 'img2video') {
      // 图生视频
      const result = await apiImg2VideoGenerate({
        model: model.id,
        prompt: record.prompt,
        user_id: userId,
        ratio: record.ratio,
        resolution: record.resolution,
        duration: record.duration,
        input_asset_ids: record.inputAssetIds || [],
      })
      taskId = result.task_id
    } else {
      // 文生视频
      const result = await apiVideoGenerate({
        model: model.id,
        prompt: record.prompt,
        user_id: userId,
        ratio: record.ratio,
        resolution: record.resolution,
        duration: record.duration,
      })

      if ('task_id' in result) {
        taskId = result.task_id
      } else {
        newRecord.videoUrl = result.video_url
        newRecord.status = 'done'
        saveRecords()
        return
      }
    }

    newRecord.taskId = taskId
    saveRecords()
    setTimeout(() => generating.value = false, 1500)
    resumeTaskPolling(newRecord, userId).catch(err => {
      console.error('Polling error:', err)
    })
  } catch (e: any) {
    newRecord.status = 'error'
    newRecord.errorMsg = e.message
    saveRecords()
  }
}



function downloadVideo(url: string, filename?: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename || url.split('/').pop() || 'video.mp4'
  a.click()
}

// tabs: txt2video | img2video
const activeTab = ref<'txt2video' | 'img2video'>('txt2video')

// model source: local | api
const modelSource = ref<'local' | 'api'>('api')

// API 模式状态
const apiModels = ref<ApiModel[]>([])
const apiModel = ref('')

const prompt = ref('')
const videoUrl = ref('')
const generating = ref(false)
const errorMsg = ref('')
const justSubmitted = ref(false)

// 视频参数
const ratio = ref('16:9')
const resolution = ref('720p')
const duration = ref(8)

const ratioOptions = [
  { label: '16:9', value: '16:9' },
  { label: '4:3', value: '4:3' },
  { label: '1:1', value: '1:1' },
  { label: '3:4', value: '3:4' },
  { label: '9:16', value: '9:16' },
  { label: '21:9', value: '21:9' },
  { label: 'adaptive', value: 'adaptive' },
]

const resolutionOptions = [
  { label: '480p', value: '480p' },
  { label: '720p', value: '720p' },
  { label: '1080p', value: '1080p' },
]

const inputFiles = ref<File[]>([])
const inputPreviews = ref<Array<{url: string, type: 'image' | 'video'}>>([])
const showAssetPicker = ref(false)
const selectedAssetIds = ref<number[]>([])
const selectedAssetPreviews = ref<Array<{id: number, url: string, type: 'image' | 'video'}>>([])

const promptInputRef = ref<InstanceType<typeof ElInput> | null>(null)
const atMentionActive = ref(false)
const atMentionStartIdx = ref(-1)
const atMentionIndex = ref(-1)

const allMediaItems = computed(() => [
  ...inputPreviews.value,
  ...selectedAssetPreviews.value,
])

const isImg2Video = computed(() => activeTab.value === 'img2video')

const maxImages = 9
const maxVideos = 3
const maxTotal = 12

function onPromptKeyup(e: KeyboardEvent) {
  if (e.key === '@') {
    if (allMediaItems.value.length === 0) return
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
  const count = allMediaItems.value.length
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
  const media = allMediaItems.value[idx]
  const label = `@${media.type === 'video' ? '视频' : '图'}${idx + 1}`
  const start = atMentionStartIdx.value
  const before = prompt.value.slice(0, start)
  const after = prompt.value.slice(start + 1)
  prompt.value = `${before}${label} ${after}`
  atMentionActive.value = false
  atMentionIndex.value = -1
  textarea.focus()
}

onMounted(async () => {
  // 加载 API 模型
  try {
    apiModels.value = await getApiModels('video')
    if (apiModels.value.length > 0) apiModel.value = apiModels.value[0].id
  } catch {}

  const userId = getCurrentUserId()

  // 从数据库加载历史，合并到 records（以 DB 为准，保留本地进行中的任务）
  if (userId) {
    const dbRecords = await historyDb.load(userId, 'video')
    const localPending = (records.value as VideoRecord[]).filter(r => r.status === 'generating')
    const fromDb: VideoRecord[] = dbRecords
      .map(r => ({
        id: String(r.id),
        dbId: r.id,
        createdAt: 0,
        prompt: r.prompt || '',
        modelName: r.model_name || '',
        ratio: '',
        resolution: '',
        duration: 0,
        status: 'done' as const,
        mode: 'txt2video' as const,
        videoUrl: r.output_urls.find(o => o.type === 'video')?.url || r.output_urls[0]?.url,
        inputAssetIds: r.input_asset_ids,
        inputAssetUrls: r.input_asset_urls || [],
      }))
    records.value = [...localPending, ...fromDb] as any
    saveRecords()
  }

  // 恢复刷新前未完成的 API 任务
  const pending = (records.value as VideoRecord[]).filter(r => r.status === 'generating' && r.taskId)
  for (const rec of pending) {
    resumeTaskPolling(rec, userId)
  }
})

function handleFilesChange(files: FileList | null) {
  if (!files || files.length === 0) return

  const newFiles: File[] = []
  const newPreviews: Array<{url: string, type: 'image' | 'video'}> = []

  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    const isVideo = file.type.startsWith('video/')
    const isImage = file.type.startsWith('image/')

    if (!isVideo && !isImage) continue

    newFiles.push(file)
    newPreviews.push({
      url: URL.createObjectURL(file),
      type: isVideo ? 'video' : 'image'
    })
  }

  // 检查数量限制
  const totalImages = [...inputPreviews.value, ...newPreviews].filter(p => p.type === 'image').length
  const totalVideos = [...inputPreviews.value, ...newPreviews].filter(p => p.type === 'video').length
  const total = inputFiles.value.length + newFiles.length + selectedAssetIds.value.length

  if (totalImages > maxImages) {
    errorMsg.value = `最多只能上传 ${maxImages} 张图片`
    return
  }
  if (totalVideos > maxVideos) {
    errorMsg.value = `最多只能上传 ${maxVideos} 个视频`
    return
  }
  if (total > maxTotal) {
    errorMsg.value = `最多只能上传 ${maxTotal} 个素材`
    return
  }

  // 追加文件，不清空资产选择
  inputFiles.value.push(...newFiles)
  inputPreviews.value.push(...newPreviews)
}

function removeFile(index: number) {
  URL.revokeObjectURL(inputPreviews.value[index].url)
  inputFiles.value.splice(index, 1)
  inputPreviews.value.splice(index, 1)
}

// 图片预览
const showImageViewer = ref(false)
const previewImageUrl = ref('')
function previewImage(url: string) {
  previewImageUrl.value = url
  showImageViewer.value = true
}

// 图片编辑器
const showEditor = ref(false)
const editingSource = ref<'file' | 'asset'>('file')
const editingFileIndex = ref(-1)
const editingAssetIndex = ref(-1)

function openLocalEditor(index: number) {
  editingSource.value = 'file'
  editingFileIndex.value = index
  showEditor.value = true
}

function openAssetEditor(index: number) {
  editingSource.value = 'asset'
  editingAssetIndex.value = index
  showEditor.value = true
}

function onEditorCancel() {
  showEditor.value = false
}

// 历史记录编辑面板
const showRecordEditor = ref(false)
const editingRecordId = ref('')
const recordEditorPrompt = ref('')
const recordEditorVideoUrl = ref('')
const recordEditorInputUrls = ref<Array<{ url: string; type: string }>>([])
const recordEditorEditedFile = ref<File | null>(null)
const recordEditorEditedPreview = ref('')
const recordEditorEditingSrc = ref('')
const showRecordImageEditor = ref(false)

function handleRecordEdit(id: string) {
  const rec = (records.value as VideoRecord[]).find(r => r.id === id)
  if (!rec || rec.status !== 'done') return
  editingRecordId.value = id
  recordEditorPrompt.value = rec.prompt
  recordEditorVideoUrl.value = rec.videoUrl || ''
  recordEditorInputUrls.value = rec.inputAssetUrls || []
  recordEditorEditedFile.value = null
  recordEditorEditedPreview.value = ''
  showRecordEditor.value = true
}

function openRecordImageEditor(src: string) {
  recordEditorEditingSrc.value = src
  showRecordImageEditor.value = true
}

function onRecordImageEditorConfirm(file: File) {
  recordEditorEditedFile.value = file
  recordEditorEditedPreview.value = URL.createObjectURL(file)
  showRecordImageEditor.value = false
}

function onRecordImageEditorCancel() {
  showRecordImageEditor.value = false
}

async function generateFromEdit() {
  if (!apiModel.value) { errorMsg.value = '请先选择 API 模型'; return }
  showRecordEditor.value = false

  const model = apiModels.value.find(m => m.id === apiModel.value)
  if (!model) { errorMsg.value = '找不到对应模型'; return }

  const userId = getCurrentUserId()
  const newRecord: VideoRecord = {
    id: generateUUID(),
    createdAt: Date.now(),
    prompt: recordEditorPrompt.value,
    modelName: model.name,
    modelId: Number(apiModel.value) || undefined,
    ratio: ratio.value,
    resolution: resolution.value,
    duration: duration.value,
    status: 'generating',
    mode: 'img2video',
  }
  records.value.unshift(newRecord)
  saveRecords()

  try {
    let inputAssetIds: number[] = []
    if (recordEditorEditedFile.value) {
      const uploaded = await uploadInputImage(recordEditorEditedFile.value, userId ?? 1)
      inputAssetIds = [uploaded.id]
    } else if (recordEditorInputUrls.value.length > 0) {
      // 复用原有 asset ids（从原记录取）
      const origRec = (records.value as VideoRecord[]).find(r => r.id === editingRecordId.value)
      inputAssetIds = origRec?.inputAssetIds || []
    }

    newRecord.inputAssetIds = inputAssetIds

    const result = await apiImg2VideoGenerate({
      model: model.id,
      prompt: newRecord.prompt,
      user_id: userId,
      ratio: newRecord.ratio,
      resolution: newRecord.resolution,
      duration: newRecord.duration,
      input_asset_ids: inputAssetIds,
    })

    newRecord.taskId = result.task_id
    saveRecords()
    resumeTaskPolling(newRecord, userId).catch(err => console.error('Polling error:', err))
  } catch (e: any) {
    newRecord.status = 'error'
    newRecord.errorMsg = e.message
    saveRecords()
  }
}

function onEditorConfirmUnified(file: File) {
  if (editingSource.value === 'file') {
    const idx = editingFileIndex.value
    if (idx >= 0 && idx < inputFiles.value.length) {
      URL.revokeObjectURL(inputPreviews.value[idx].url)
      inputFiles.value[idx] = file
      inputPreviews.value[idx] = { url: URL.createObjectURL(file), type: 'image' }
    }
  } else {
    const idx = editingAssetIndex.value
    if (idx >= 0 && idx < selectedAssetPreviews.value.length) {
      // 从资产列表移除，加入本地文件列表
      selectedAssetIds.value.splice(idx, 1)
      selectedAssetPreviews.value.splice(idx, 1)
      inputFiles.value.push(file)
      inputPreviews.value.push({ url: URL.createObjectURL(file), type: 'image' })
    }
  }
  showEditor.value = false
}

function removeAsset(index: number) {
  selectedAssetIds.value.splice(index, 1)
  selectedAssetPreviews.value.splice(index, 1)
}

function clearAllInputs() {
  inputPreviews.value.forEach(p => URL.revokeObjectURL(p.url))
  inputFiles.value = []
  inputPreviews.value = []
  selectedAssetIds.value = []
  selectedAssetPreviews.value = []
}

function openAssetPicker() {
  showAssetPicker.value = true
}

function handleAssetSelect(assets: Array<{ id: number; location: string; asset_type?: string }>) {
  // 检查数量限制
  const newAssets = assets.filter(a => !selectedAssetIds.value.includes(a.id))

  const totalImages = [...inputPreviews.value.filter(p => p.type === 'image'), ...selectedAssetPreviews.value.filter(p => p.type === 'image'), ...newAssets.filter(a => a.asset_type === 'picture')].length
  const totalVideos = [...inputPreviews.value.filter(p => p.type === 'video'), ...selectedAssetPreviews.value.filter(p => p.type === 'video'), ...newAssets.filter(a => a.asset_type === 'video')].length
  const total = inputFiles.value.length + selectedAssetIds.value.length + newAssets.length

  if (totalImages > maxImages) {
    errorMsg.value = `最多只能选择 ${maxImages} 张图片`
    return
  }
  if (totalVideos > maxVideos) {
    errorMsg.value = `最多只能选择 ${maxVideos} 个视频`
    return
  }
  if (total > maxTotal) {
    errorMsg.value = `最多只能选择 ${maxTotal} 个素材`
    return
  }

  // 追加资产，不清空本地上传
  for (const asset of newAssets) {
    selectedAssetIds.value.push(asset.id)
    const isVideo = asset.asset_type === 'video'
    selectedAssetPreviews.value.push({
      id: asset.id,
      url: `/api/view?filename=${encodeURIComponent(asset.location.replace(/\\/g, '/').split('/').pop()!)}&type=output`,
      type: isVideo ? 'video' : 'image'
    })
  }
}

async function resumeTaskPolling(record: VideoRecord, userId?: number) {
  if (!record.taskId) return
  console.log('[Video] Start polling task:', record.taskId)
  try {
    // 先查一次状态，避免重复轮询已完成的任务
    const checkUrl = userId ? `/api/api-proxy/task/${record.taskId}?user_id=${userId}` : `/api/api-proxy/task/${record.taskId}`
    const checkRes = await fetch(checkUrl)
    if (checkRes.ok) {
      const checkData = await checkRes.json()
      console.log('[Video] Task status:', checkData)
      if (checkData.status === 'completed' && checkData.result) {
        console.log('[Video] Task completed, result:', checkData.result)
        const rec = records.value.find(r => r.id === record.id)
        if (rec) {
          const videoItem = checkData.result.find((item: any) => item.type === 'video')
          console.log('[Video] Found video item:', videoItem)
          rec.videoUrl = videoItem?.url || ''
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
    console.log('[Video] Starting pollTaskUntilDone')
    const { pollTaskUntilDone } = await import('../api/apiService')
    const result = await pollTaskUntilDone(record.taskId, userId, 'video')
    console.log('[Video] Poll completed, result:', result)
    const rec = records.value.find(r => r.id === record.id)
    if (rec) {
      const videoItem = result.images.find(item => item.url)
      console.log('[Video] Found video in result:', videoItem)
      rec.videoUrl = videoItem?.url || ''
      rec.status = 'done'
      if ((result as any).historyId) rec.dbId = (result as any).historyId
      saveRecords()
    }
  } catch (e: any) {
    console.error('[Video] Polling error:', e)
    const rec = records.value.find(r => r.id === record.id)
    if (rec) {
      rec.status = 'error'
      rec.errorMsg = e.message
      saveRecords()
    }
  }
}

async function handleGenerate() {
  errorMsg.value = ''
  videoUrl.value = ''

  if (!prompt.value.trim()) {
    errorMsg.value = '请输入提示词'
    return
  }

  // 防止重复提交
  if (generating.value) {
    console.warn('[handleGenerate] Already generating, ignoring duplicate request')
    return
  }

  // 立即设置 generating 状态，防止重复点击
  generating.value = true

  // ── API 调用模式 ──
  if (modelSource.value === 'api') {
    if (!apiModel.value) {
      errorMsg.value = '请先在模型管理中添加视频模型'
      generating.value = false
      return
    }

    // 图生视频：提前校验图片
    if (activeTab.value === 'img2video' && inputFiles.value.length === 0 && selectedAssetIds.value.length === 0) {
      errorMsg.value = '请上传图片/视频或从资产选择'
      generating.value = false
      return
    }

    const modelName = apiModels.value.find(m => m.id === apiModel.value)?.name || apiModel.value
    const currentPrompt = prompt.value

    const record: VideoRecord = {
      id: generateUUID(),
      createdAt: Date.now(),
      prompt: currentPrompt,
      modelId: Number(apiModel.value) || undefined,
    modelName,
      ratio: ratio.value,
      resolution: resolution.value,
      duration: duration.value,
      status: 'generating',
      mode: activeTab.value,
      inputAssetIds: activeTab.value === 'img2video' ? [...selectedAssetIds.value] : undefined,
    }
    records.value.unshift(record)
    saveRecords()

    justSubmitted.value = true
    setTimeout(() => justSubmitted.value = false, 1000)

    // 获取 user_id
    const userId = getCurrentUserId()

    try {
      let taskId: string

      // 图生视频模式
      if (activeTab.value === 'img2video') {

        console.log('[handleGenerate] inputFiles:', inputFiles.value.length, 'selectedAssetIds:', selectedAssetIds.value.length)
        console.log('[handleGenerate] inputFiles details:', inputFiles.value.map(f => ({ name: f.name, size: f.size, type: f.type })))

        // 先把本地上传的文件存入 input_assets 表，拿到 ID
        const uploadedIds: number[] = []
        for (const file of inputFiles.value) {
          const res = await uploadInputImage(file, userId!)
          uploadedIds.push(res.id)
        }
        const allAssetIds = [...uploadedIds, ...selectedAssetIds.value]
        record.inputAssetIds = allAssetIds

        const result = await apiImg2VideoGenerate({
          model: apiModel.value,
          prompt: currentPrompt,
          user_id: userId,
          ratio: ratio.value,
          resolution: resolution.value,
          duration: duration.value,
          input_asset_ids: allAssetIds,
        })

        taskId = result.task_id
      }
      // 文生视频模式
      else {
        const result = await apiVideoGenerate({
          model: apiModel.value,
          prompt: currentPrompt,
          user_id: userId,
          ratio: ratio.value,
          resolution: resolution.value,
          duration: duration.value,
        })

        if ('task_id' in result) {
          taskId = result.task_id
        } else {
          // 直接返回结果
          videoUrl.value = result.video_url
          record.videoUrl = result.video_url
          record.status = 'done'
          saveRecords()
          generating.value = false
          return
        }
      }

      // 异步任务，任务已提交
      record.taskId = taskId
      saveRecords()

      // 1.5秒后释放按钮
      setTimeout(() => {
        generating.value = false
      }, 1500)

      // 开始轮询（不阻塞，后台执行）
      resumeTaskPolling(record, userId).catch(err => {
        console.error('Polling error:', err)
      })
    } catch (e: any) {
      errorMsg.value = 'API 生成失败：' + e.message
      record.status = 'error'
      record.errorMsg = e.message
      saveRecords()
      generating.value = false
    }
    return
  }

  // ── 本地 ComfyUI 模式 ──
  errorMsg.value = '本地视频生成暂未实现，请使用 API 调用'
}
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
          <button class="tab-btn" :class="{ active: activeTab === 'txt2video' }" @click="activeTab = 'txt2video'">文生视频</button>
          <button class="tab-btn" :class="{ active: activeTab === 'img2video' }" @click="activeTab = 'img2video'">图生视频</button>
        </div>

        <div class="panel-body">
          <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

          <!-- model source toggle -->
          <div class="row-item">
            <span class="row-label">调用方式</span>
            <div class="source-toggle">
              <button :class="{ active: modelSource === 'local' }" @click="modelSource = 'local'">本地模型</button>
              <button :class="{ active: modelSource === 'api' }" @click="modelSource = 'api'">API 调用</button>
            </div>
          </div>

          <!-- API model select -->
          <div v-if="modelSource === 'api' && apiModels.length > 0" class="row-item">
            <span class="row-label">API 模型</span>
            <ElSelect v-model="apiModel" placeholder="选择模型" class="row-select">
              <ElOption v-for="m in apiModels" :key="m.id" :label="m.name" :value="m.id" />
            </ElSelect>
          </div>
          <div v-else-if="modelSource === 'api'" class="api-tip">
            <span>请先在</span>
            <router-link to="/models" class="api-tip-link">模型管理</router-link>
            <span>中添加视频模型</span>
          </div>
          <div v-else class="api-tip">
            <span>本地视频生成暂未实现</span>
          </div>

          <div class="divider" />

          <!-- 视频参数 -->
          <div class="row-item">
            <span class="row-label">比例</span>
            <div class="filter-group">
              <button
                v-for="opt in ratioOptions"
                :key="opt.value"
                class="filter-btn"
                :class="{ active: ratio === opt.value }"
                @click="ratio = opt.value"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>

          <div class="row-item">
            <span class="row-label">分辨率</span>
            <div class="filter-group">
              <button
                v-for="opt in resolutionOptions"
                :key="opt.value"
                class="filter-btn"
                :class="{ active: resolution === opt.value }"
                @click="resolution = opt.value"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>

          <div class="row-item">
            <span class="row-label">时长(秒)</span>
            <div class="stepper">
              <button class="stepper-btn" @click="duration = Math.max(1, duration - 1)">−</button>
              <input
                v-model.number="duration"
                type="number"
                class="stepper-input"
                :min="1"
                :max="60"
              />
              <button class="stepper-btn" @click="duration = Math.min(60, duration + 1)">+</button>
            </div>
          </div>

          <div class="divider" />

          <!-- img2video upload -->
          <template v-if="activeTab === 'img2video'">
            <div class="section-label">输入素材（图片最多9张，视频最多3个，总计最多12个）</div>

            <!-- 已上传文件预览 -->
            <div v-if="inputPreviews.length > 0" class="previews-grid">
              <div v-for="(preview, index) in inputPreviews" :key="'file-' + index" class="preview-item">
                <video v-if="preview.type === 'video'" :src="preview.url" class="preview-media" />
                <img v-else :src="preview.url" class="preview-media" />
                <button v-if="preview.type === 'image'" class="edit-btn" @click="openLocalEditor(index)" title="编辑图片">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19l7-7-3-3-7 7v3h3z"/><path d="M18 13l1.5-1.5a2.12 2.12 0 0 0-3-3L15 10"/></svg>
                </button>
                <button class="remove-btn" @click="removeFile(index)">×</button>
                <span class="preview-badge">{{ preview.type === 'video' ? '视频' : '图片' }}{{ index + 1 }}</span>
              </div>
            </div>

            <!-- 已选择资产预览 -->
            <div v-if="selectedAssetPreviews.length > 0" class="previews-grid">
              <div v-for="(preview, index) in selectedAssetPreviews" :key="'asset-' + preview.id" class="preview-item">
                <video v-if="preview.type === 'video'" :src="preview.url" class="preview-media" />
                <img v-else :src="preview.url" class="preview-media" />
                <button v-if="preview.type === 'image'" class="edit-btn" @click="openAssetEditor(index)" title="编辑图片">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19l7-7-3-3-7 7v3h3z"/><path d="M18 13l1.5-1.5a2.12 2.12 0 0 0-3-3L15 10"/></svg>
                </button>
                <button class="remove-btn" @click="removeAsset(index)">×</button>
                <span class="preview-badge">{{ preview.type === 'video' ? '视频' : '图片' }}{{ inputPreviews.length + index + 1 }}</span>
              </div>
            </div>

            <!-- 上传按钮 -->
            <div class="upload-actions">
              <button class="asset-btn" @click="openAssetPicker">
                <span>从资产选择</span>
              </button>
              <label class="local-upload-btn">
                <input type="file" accept="image/*,video/*" multiple @change="(e) => handleFilesChange((e.target as HTMLInputElement).files)" hidden />
                <el-icon><UploadFilled /></el-icon>
                <span>本地上传</span>
              </label>
              <button v-if="inputPreviews.length > 0 || selectedAssetPreviews.length > 0" class="clear-all-btn-small" @click="clearAllInputs">
                清空全部
              </button>
            </div>
          </template>

          <!-- prompt -->
          <div class="section-label">
            {{ activeTab === 'txt2video' ? '描述你想生成的视频' : '描述生成方向' }}
            <span v-if="activeTab === 'img2video' && allMediaItems.length > 0" class="prompt-hint">
              （已上传{{ allMediaItems.length }}个素材，@ 引用）
            </span>
          </div>
          <div class="prompt-wrap">
            <ElInput
              ref="promptInputRef"
              v-model="prompt"
              type="textarea" :rows="6"
              :placeholder="activeTab === 'txt2video' ? '输入提示词，描述视频内容、场景、动作...（@ 选参考素材）' : '描述生成方向...（@ 选参考素材）'"
              class="prompt-input"
              @keyup="onPromptKeyup"
              @keydown="onPromptKeydown"
              @blur="atMentionActive = false"
            />
            <div v-if="atMentionActive && allMediaItems.length > 0" class="mention-dropdown">
              <div
                v-for="(media, idx) in allMediaItems"
                :key="idx"
                class="mention-item"
                :class="{ active: atMentionIndex === idx }"
                @mousedown.prevent="insertMention(idx)"
              >
                <video v-if="media.type === 'video'" :src="media.url" class="mention-thumb" />
                <img v-else :src="media.url" class="mention-thumb" />
                <span>@{{ media.type === 'video' ? '视频' : '图' }}{{ idx + 1 }}</span>
              </div>
            </div>
          </div>

          <!-- generate -->
          <button class="generate-btn" :class="{ loading: generating, submitted: justSubmitted }" :disabled="generating" @click="handleGenerate">
            <span class="btn-glow" />
            <span class="btn-label">{{ justSubmitted ? '已提交 ✓' : generating ? '生成中...' : '开始生成' }}</span>
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

          <div v-for="rec in filteredRecords" :key="rec.id" class="record-row">
            <!-- 左侧输入图 -->
            <div class="record-input-col">
              <template v-if="rec.inputAssetUrls && rec.inputAssetUrls.length">
                <template v-for="(a, i) in rec.inputAssetUrls" :key="i">
                  <video v-if="a.type === 'video'" :src="a.url" class="input-panel-thumb" controls />
                  <img v-else :src="a.url" class="input-panel-thumb" @click="previewImage(a.url)" />
                </template>
              </template>
            </div>
            <!-- 右侧卡片 -->
            <RecordCard class="record-card-flex" :record="rec" @delete="deleteRecord" @retry="(r) => retryRecord(r as any)" @edit="handleRecordEdit">
              <template #meta>
                <div class="card-params">
                  <span>{{ rec.ratio }}</span>
                  <span>·</span>
                  <span>{{ rec.resolution }}</span>
                  <span>·</span>
                  <span>{{ rec.duration }}s</span>
                </div>
              </template>
              <template #prompt>
                <p class="card-prompt">{{ rec.prompt }}</p>
              </template>
              <template #result>
                <div v-if="rec.videoUrl" class="card-video">
                  <video :src="rec.videoUrl" controls class="video-player" />
                  <button class="download-btn" @click="downloadVideo(rec.videoUrl)" title="下载">
                    <span>⬇</span>
                  </button>
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
      :max-select="12"
      :allow-video="true"
      @select="handleAssetSelect"
    />

    <!-- Image Viewer -->
    <el-image-viewer
      v-if="showImageViewer"
      :url-list="[previewImageUrl]"
      @close="showImageViewer = false"
      :hide-on-click-modal="true"
    />

    <!-- Image Editor（输入素材编辑） -->
    <ImageEditor
      v-if="showEditor"
      :image-src="editingSource === 'file' ? (inputPreviews[editingFileIndex]?.url ?? '') : (selectedAssetPreviews[editingAssetIndex]?.url ?? '')"
      :visible="showEditor"
      @confirm="onEditorConfirmUnified"
      @cancel="onEditorCancel"
    />

    <!-- 历史记录编辑面板 -->
    <div v-if="showRecordEditor" class="record-edit-overlay" @click.self="showRecordEditor = false">
      <div class="record-edit-panel">
        <div class="record-edit-header">
          <span class="record-edit-title">编辑并继续生成</span>
          <button class="record-edit-close" @click="showRecordEditor = false">×</button>
        </div>

        <!-- 输入图预览 + 编辑入口 -->
        <template v-if="recordEditorInputUrls.length > 0">
          <div class="record-edit-label">输入素材</div>
          <div class="record-edit-images">
            <div
              v-for="(a, i) in recordEditorInputUrls"
              :key="i"
              class="record-edit-img-wrap"
            >
              <video v-if="a.type === 'video'" :src="a.url" class="record-edit-img" controls />
              <img v-else :src="i === 0 && recordEditorEditedPreview ? recordEditorEditedPreview : a.url" class="record-edit-img" />
              <button
                v-if="a.type !== 'video'"
                class="record-edit-img-btn"
                @click="openRecordImageEditor(i === 0 && recordEditorEditedPreview ? recordEditorEditedPreview : a.url)"
                title="编辑此图"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 19l7-7-3-3-7 7v3h3z"/>
                  <path d="M18 13l1.5-1.5a2.12 2.12 0 0 0-3-3L15 10"/>
                </svg>
                编辑
              </button>
              <span v-if="i === 0 && recordEditorEditedPreview" class="record-edit-badge">已编辑</span>
            </div>
          </div>
        </template>

        <!-- 提示词 -->
        <div class="record-edit-label">提示词</div>
        <textarea
          v-model="recordEditorPrompt"
          class="record-edit-textarea"
          rows="4"
          placeholder="修改提示词..."
        />

        <button class="record-edit-generate-btn" @click="generateFromEdit">
          <span>继续生成</span>
        </button>
      </div>
    </div>

    <!-- 历史记录图片编辑器 -->
    <ImageEditor
      v-if="showRecordImageEditor"
      :image-src="recordEditorEditingSrc"
      :visible="showRecordImageEditor"
      @confirm="onRecordImageEditorConfirm"
      @cancel="onRecordImageEditorCancel"
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
}

.prompt-hint {
  color: rgba(167,139,250,0.6);
  font-size: 10px;
  margin-left: 8px;
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

/* filter group */
.filter-group {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.filter-btn {
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.03);
  color: rgba(255,255,255,0.5);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-btn:hover {
  border-color: rgba(108,99,255,0.3);
  background: rgba(108,99,255,0.05);
}

.filter-btn.active {
  border-color: rgba(108,99,255,0.6);
  background: rgba(108,99,255,0.2);
  color: rgba(255,255,255,0.9);
}

.duration-input {
  width: 120px;
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
  width: 120px;
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
.api-tip-link {
  color: rgba(167,139,250,0.8);
  text-decoration: underline;
}

/* upload actions */
.upload-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.asset-btn, .local-upload-btn {
  flex: 1;
  min-width: 120px;
  height: 60px;
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

.clear-all-btn-small {
  height: 60px;
  padding: 0 16px;
  border-radius: 10px;
  border: 1px solid rgba(248,113,113,0.2);
  background: rgba(248,113,113,0.1);
  color: #f87171;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.clear-all-btn-small:hover {
  background: rgba(248,113,113,0.2);
  border-color: rgba(248,113,113,0.4);
}

/* previews grid */
.previews-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.preview-item {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(0,0,0,0.3);
}

.preview-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.remove-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(0,0,0,0.7);
  border: none;
  color: white;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.remove-btn:hover {
  background: rgba(220,50,50,0.9);
  transform: scale(1.1);
}

.edit-btn {
  position: absolute;
  top: 4px;
  right: 28px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(0,0,0,0.6);
  border: none;
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  z-index: 2;
}
.edit-btn:hover {
  background: rgba(108,99,255,0.9);
  transform: scale(1.1);
}

.preview-badge {
  position: absolute;
  bottom: 4px;
  left: 4px;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(0,0,0,0.7);
  color: rgba(255,255,255,0.8);
  font-size: 10px;
}

/* generate button */
.generate-btn {
  position: relative;
  width: 100%;
  height: 46px;
  margin-top: 8px;
  border-radius: 12px;
  border: none;
  cursor: pointer;
  overflow: hidden;
  background: linear-gradient(135deg, #6c63ff, #a78bfa, #6c63ff);
  background-size: 200% auto;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 2px;
  transition: opacity 0.2s, transform 0.15s;
  animation: shimmer 3s linear infinite;
}
.generate-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  opacity: 0.9;
}
.generate-btn:active:not(:disabled) {
  transform: translateY(0);
}
.generate-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  animation: none;
}
.generate-btn.loading {
  animation: breathe 2s ease-in-out infinite;
}
.generate-btn.submitted {
  background: linear-gradient(135deg, #22c55e, #4ade80, #22c55e);
  background-size: 200% auto;
  animation: shimmer 1s linear infinite;
}

.btn-glow {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: inherit;
  filter: blur(12px);
  opacity: 0;
  transition: opacity 0.3s;
  z-index: -1;
}
.generate-btn:not(:disabled):hover .btn-glow {
  opacity: 0.5;
}
.btn-label {
  position: relative;
  z-index: 1;
}

.error-msg {
  color: #f87171;
  font-size: 12px;
  padding: 8px 12px;
  background: rgba(248,113,113,0.07);
  border-radius: 8px;
  border: 1px solid rgba(248,113,113,0.18);
}

/* ── Right panel ── */
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-start;
  padding: 24px 24px 24px 20px;
  overflow-y: auto;
}

.empty-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  flex: 1;
}
.empty-orb {
  width: 60px;
  height: 60px;
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

/* message stream */
.stream {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ── 每条记录行 ── */
.record-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.record-input-col {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px 0;
}
.record-card-flex {
  flex: 1;
  min-width: 0;
}
.input-panel-thumb {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.08);
  display: block;
  transition: transform 0.15s, border-color 0.15s;
}
img.input-panel-thumb {
  cursor: zoom-in;
}
.input-panel-thumb:hover {
  transform: scale(1.03);
  border-color: rgba(108,99,255,0.4);
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
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.card-preview-img {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.1);
}

.card-model-name {
  font-size: 11px;
  color: rgba(108,99,255,0.8);
  margin-top: 4px;
}

.card-params {
  font-size: 11px;
  color: rgba(255,255,255,0.35);
  display: flex;
  gap: 6px;
}

.card-prompt {
  font-size: 13px;
  color: rgba(255,255,255,0.7);
  line-height: 1.6;
  margin: 0;
  word-break: break-all;
}

/* generating state */
/* video */
.card-video {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background: #000;
}

.video-player {
  width: 100%;
  max-height: 400px;
  display: block;
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
  transition: all 0.2s;
}
.download-btn:hover {
  background: rgba(108,99,255,0.9);
  transform: scale(1.1);
}

@keyframes breathe {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(0.95);
  }
}

@keyframes pulse-dot {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

@keyframes shimmer {
  0% {
    background-position: 0% center;
  }
  100% {
    background-position: 200% center;
  }
}

/* 历史记录左侧输入图 */
.hist-input-thumb {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.08);
  display: block;
  transition: transform 0.15s, border-color 0.15s;
}
.hist-input-thumb:hover {
  transform: scale(1.06);
  border-color: rgba(108,99,255,0.4);
}

/* 历史记录左侧输入图 */
.hist-input-col {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
  width: 100%;
  align-content: start;
}
.hist-input-thumb {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.08);
  display: block;
  transition: transform 0.15s, border-color 0.15s;
}
img.hist-input-thumb {
  cursor: zoom-in;
}
.hist-input-thumb:hover {
  transform: scale(1.04);
  border-color: rgba(108,99,255,0.4);
}

/* ── 每条记录行 ── */
.record-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}
.record-input-col {
  width: 200px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px 0;
}
.record-card-flex {
  flex: 1;
  min-width: 0;
}
.input-panel-thumb {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.08);
  display: block;
  transition: transform 0.15s, border-color 0.15s;
}
img.input-panel-thumb {
  cursor: zoom-in;
}
.input-panel-thumb:hover {
  transform: scale(1.03);
  border-color: rgba(108,99,255,0.4);
}

/* 历史记录编辑面板 */
.record-edit-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: flex-end;
}
.record-edit-panel {
  width: 380px;
  max-width: 95vw;
  height: 100vh;
  background: #16162a;
  border-left: 1px solid rgba(108,99,255,0.2);
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px 20px;
  overflow-y: auto;
}
.record-edit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.record-edit-title {
  font-size: 14px;
  color: rgba(255,255,255,0.85);
  font-weight: 500;
}
.record-edit-close {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: none;
  border: 1px solid rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.4);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.record-edit-close:hover {
  background: rgba(248,113,113,0.15);
  border-color: rgba(248,113,113,0.3);
  color: #f87171;
}
.record-edit-images {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.record-edit-img-wrap {
  position: relative;
  flex-shrink: 0;
}
.record-edit-img {
  width: 160px;
  height: 160px;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.08);
  display: block;
}
.record-edit-img-btn {
  position: absolute;
  bottom: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(0,0,0,0.7);
  border: 1px solid rgba(108,99,255,0.4);
  color: rgba(167,139,250,0.9);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}
.record-edit-img-btn:hover {
  background: rgba(108,99,255,0.4);
}
.record-edit-badge {
  position: absolute;
  top: 6px;
  left: 6px;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(108,99,255,0.7);
  color: white;
}
.record-edit-label {
  font-size: 11px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 0.5px;
}
.record-edit-textarea {
  width: 100%;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 10px;
  color: rgba(255,255,255,0.8);
  font-size: 13px;
  line-height: 1.6;
  padding: 10px 12px;
  resize: vertical;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.2s;
}
.record-edit-textarea:focus {
  border-color: rgba(108,99,255,0.4);
}
.record-edit-generate-btn {
  width: 100%;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(108,99,255,0.8), rgba(167,139,250,0.6));
  border: 1px solid rgba(108,99,255,0.4);
  color: white;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  margin-top: auto;
}
.record-edit-generate-btn:hover {
  background: linear-gradient(135deg, rgba(108,99,255,1), rgba(167,139,250,0.8));
}

@media (max-width: 900px) {
  .layout {
    flex-direction: column;
    height: auto;
  }
  .left-panel {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }
  .right-panel {
    padding: 24px 20px;
  }
}
</style>
