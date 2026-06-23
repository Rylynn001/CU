<script setup lang="ts">
defineOptions({ name: 'TextToVideo' })
// Vue 核心
import { ref, onMounted, computed } from 'vue'
// Element Plus UI 组件
import { ElInput, ElSelect, ElOption, ElImageViewer } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
// 资产选择器弹窗
import AssetPicker from '../components/AssetPicker.vue'
// 视频播放器弹窗（点击历史记录中的视频时打开）
import VideoPlayer from '../components/VideoPlayer.vue'
// 历史记录卡片
import RecordCard from '../components/RecordCard.vue'
// 图片编辑器（图生视频时可以涂抹参考图）
import ImageEditor from '../components/ImageEditor.vue'
import ModelViewer from '../components/ModelViewer.vue'
// 后端 API 接口
import { getApiModels, retryHistory, favoriteAsset, type ApiModel } from '../api/apiService'
// 历史记录管理
import { useGenerationHistory } from '../composables/useGenerationHistory'
// 任务轮询
import { useTaskPolling } from '../composables/useTaskPolling'
// @提及功能
import { useAtMention } from '../composables/useAtMention'
// 历史记录编辑面板
import { useRecordEditor } from '../composables/useRecordEditor'
// 输入媒体管理：统一管理本地上传文件和资产库选择的图片/视频
import { useInputMedia } from '../composables/useInputMedia'
// 视频生成服务：文生视频 和 图生视频 的 API 调用封装
import { submitVideoGeneration, submitImg2VideoGeneration } from '../services/videoGenerationService'
import { getCurrentUserId } from '../utils/user'
import { generateUUID } from '../utils/uuid'

// ── 生成记录类型 ──────────────────────────────────────────
interface VideoRecord {
  id: string                                            // 前端唯一 ID
  createdAt: number                                     // 创建时间戳
  prompt: string                                        // 提示词
  modelName: string                                     // 模型名称
  ratio: string                                         // 宽高比（如 "16:9"）
  resolution: string                                    // 分辨率（如 "720p"）
  duration: number                                      // 视频时长（秒）
  status: 'generating' | 'done' | 'error'              // 当前状态
  videoUrl?: string                                     // 生成结果视频 URL
  errorMsg?: string                                     // 失败时的错误信息
  taskId?: string                                       // API 任务 ID，用于轮询
  mode: 'txt2video' | 'img2video'                      // 文生视频 或 图生视频
  inputAssetIds?: number[]                              // 参考素材在资产库中的 ID
  inputAssetUrls?: Array<{ url: string; type: string }> // 参考素材的线上 URL（展示用）
  dbId?: number                                         // 数据库记录 ID
  modelId?: number                                      // 模型数据库 ID
  outputAssetId?: number                                // 输出视频在资产库中的 ID（用于收藏）
}

// ── 历史记录 ──────────────────────────────────────────────
const {
  records, saveRecords, searchQuery, expandedInputs, filteredRecords,
  toggleInputExpand, deleteRecord, clearAll, loadFromDb, loadMoreFromDb,
  hasMoreInDb, dbPageSize, markStaleRecords,
} = useGenerationHistory<VideoRecord>('video_generation_history', 'video',
  (r) => ({
    // blob: URL 在页面刷新后失效，保存时过滤掉，下次从数据库重新加载线上 URL
    inputAssetUrls: r.inputAssetUrls?.filter(a => !a.url.startsWith('blob:')),
  }),
)

// ── 任务轮询 ──────────────────────────────────────────────
const { resumeTaskPolling } = useTaskPolling<VideoRecord>(
  () => records.value as VideoRecord[],
  saveRecords,
)

// 对视频生成任务启动轮询，回调中将结果写入记录
function pollVideo(record: VideoRecord, userId?: number) {
  return resumeTaskPolling(record, userId, (rec, result) => {
    // 从返回的 images 数组中找到视频类型的条目
    const videoItem = result.images.find((i: any) => i.url)
    rec.videoUrl = videoItem?.url || ''
    if (videoItem?.id) rec.outputAssetId = videoItem.id
    // 如果后端返回了参考素材的线上 URL，更新到记录中（用于展示）
    if ((result as any).inputAssetUrls?.length) {
      rec.inputAssetUrls = (result as any).inputAssetUrls
    }
  }, 'video')  // 'video' 告诉轮询器这是视频任务
}

// ── 模型 ──────────────────────────────────────────────────
const apiModels = ref<ApiModel[]>([])
const apiModel = ref('')
// 视频页默认使用 API 模式（本地视频生成暂未实现）
const modelSource = ref<'local' | 'api'>('api')
// 当前标签页：文生视频 或 图生视频
const activeTab = ref<'txt2video' | 'img2video'>('txt2video')
const isImg2Video = computed(() => activeTab.value === 'img2video')

// ── 参数 ──────────────────────────────────────────────────
const prompt = ref('')
const generating = ref(false)
const errorMsg = ref('')
// 防重复提交标志
const justSubmitted = ref(false)
// 视频宽高比
const ratio = ref('16:9')
// 视频分辨率
const resolution = ref('720p')
// 视频时长（秒）
const duration = ref(8)

// 宽高比选项列表
const ratioOptions = [
  { label: '16:9', value: '16:9' },
  { label: '4:3', value: '4:3' },
  { label: '1:1', value: '1:1' },
  { label: '3:4', value: '3:4' },
  { label: '9:16', value: '9:16' },
  { label: '21:9', value: '21:9' },
  { label: 'adaptive', value: 'adaptive' },  // 自适应：由模型根据参考图决定
]

// 分辨率选项列表
const resolutionOptions = [
  { label: '480p', value: '480p' },
  { label: '720p', value: '720p' },
  { label: '1080p', value: '1080p' },
]

// ── 输入媒体 ──────────────────────────────────────────────
// 控制资产选择器弹窗
const showAssetPicker = ref(false)

// 音频文件（可选）
const audioFile = ref<File | null>(null)
const audioFileName = computed(() => audioFile.value?.name ?? '')
function handleAudioChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) audioFile.value = file
}
function removeAudio() {
  audioFile.value = null
}

// 3D 模型视角截图
const showModelViewer = ref(false)
function handleModelCapture(file: File) {
  inputFiles.value.push(file)
  inputPreviews.value.push({ url: URL.createObjectURL(file), type: 'image' })
}
// useInputMedia 统一管理图生视频的输入素材：
// inputFiles - 本地上传的文件列表
// inputPreviews - 本地文件的预览信息（url + type）
// selectedAssetIds - 从资产库选择的素材 ID 列表
// selectedAssetPreviews - 资产库素材的预览信息（url + type + id）
// allMediaItems - 合并后的所有素材（用于 @mention 下拉）
// handleFilesChange - 处理文件选择事件（支持多选，自动校验数量上限）
// removeFile / removeAsset - 删除某个本地文件 / 资产
// clearAllInputs - 清空所有输入素材
// handleAssetSelect - 资产选择器回调
// replaceFile / replaceAssetWithFile - 编辑图片后替换原素材
const {
  inputFiles, inputPreviews, selectedAssetIds, selectedAssetPreviews, allMediaItems,
  handleFilesChange, removeFile, removeAsset, clearAllInputs, handleAssetSelect,
  replaceFile, replaceAssetWithFile,
} = useInputMedia((msg) => { errorMsg.value = msg })

// ── @mention ──────────────────────────────────────────────
const promptInputRef = ref<InstanceType<typeof ElInput> | null>(null)
const { atMentionActive, atMentionIndex, onPromptKeyup, onPromptKeydown, insertMention } =
  useAtMention(
    () => prompt.value,
    (v) => { prompt.value = v },
    () => allMediaItems.value,  // @mention 可引用所有已上传的图片和视频
    promptInputRef,
  )

// ── 图片预览 ──────────────────────────────────────────────
const showImageViewer = ref(false)
const previewImageUrl = ref('')
function previewImage(url: string) {
  previewImageUrl.value = url
  showImageViewer.value = true
}

// ── 视频播放器弹窗 ────────────────────────────────────────
// 控制视频播放器弹窗的显示
const showVideoPlayer = ref(false)
// 当前播放的视频 URL
const activeVideoUrl = ref('')
// 当前播放视频对应的资产 ID（用于收藏等操作）
const activeVideoDbId = ref<number | undefined>(undefined)

// 点击历史记录中的视频缩略图时打开播放器
function openVideo(url: string, dbId?: number) {
  activeVideoUrl.value = url
  activeVideoDbId.value = dbId
  showVideoPlayer.value = true
}

// ── 图片编辑器（输入素材） ────────────────────────────────
// 控制输入素材编辑器弹窗
const showEditor = ref(false)
// 当前编辑的素材来源：本地文件 或 资产库
const editingSource = ref<'file' | 'asset'>('file')
// 当前编辑的本地文件索引
const editingFileIndex = ref(-1)
// 当前编辑的资产索引
const editingAssetIndex = ref(-1)

function openLocalEditor(index: number) {
  editingSource.value = 'file'; editingFileIndex.value = index; showEditor.value = true
}
function openAssetEditor(index: number) {
  editingSource.value = 'asset'; editingAssetIndex.value = index; showEditor.value = true
}
function onEditorCancel() { showEditor.value = false }

// 编辑器确认后，根据来源替换对应的素材
function onEditorConfirmUnified(file: File) {
  if (editingSource.value === 'file') {
    const idx = editingFileIndex.value
    if (idx >= 0 && idx < inputFiles.value.length) replaceFile(idx, file)
  } else {
    const idx = editingAssetIndex.value
    if (idx >= 0 && idx < selectedAssetPreviews.value.length) replaceAssetWithFile(idx, file)
  }
  showEditor.value = false
}

// ── 历史记录编辑面板 ──────────────────────────────────────
const inlineEditorRef = ref<InstanceType<typeof ImageEditor> | null>(null)
const {
  showRecordEditor, recordEditorPrompt,
  recordEditorEditedPreview, recordEditorEditingSrc, showRecordImageEditor,
  openEditor: openRecordEditor, onImageEditorConfirm: onRecordImageEditorConfirm,
  onImageEditorCancel: onRecordImageEditorCancel, closeEditor: closeRecordEditor, getEditedFile,
} = useRecordEditor(inlineEditorRef)

// 点击历史记录卡片的"继续生成"按钮
function handleRecordEdit(id: string) {
  const rec = (records.value as VideoRecord[]).find(r => r.id === id)
  if (!rec || rec.status !== 'done') return
  openRecordEditor(rec)
}

// 在编辑面板中点击"继续生成"按钮（图生视频模式，使用编辑后的图片重新生成）
async function generateFromEdit() {
  if (!apiModel.value) { errorMsg.value = '请先选择 API 模型'; return }
  closeRecordEditor()

  const model = apiModels.value.find(m => m.id === apiModel.value)
  if (!model) { errorMsg.value = '找不到对应模型'; return }

  const editedFile = await getEditedFile()
  const userId = getCurrentUserId()

  // 创建新记录
  const newRecord: VideoRecord = {
    id: generateUUID(), createdAt: Date.now(),
    prompt: recordEditorPrompt.value, modelName: model.name,
    modelId: Number(apiModel.value) || undefined,
    ratio: ratio.value, resolution: resolution.value, duration: duration.value,
    status: 'generating', mode: 'img2video',
  }
  records.value.unshift(newRecord)
  saveRecords()

  try {
    let inputAssetIds: number[] = []
    if (editedFile) {
      // 将编辑后的图片上传到资产库，获取资产 ID
      const { uploadInputImage } = await import('../api/apiService')
      const uploaded = await uploadInputImage(editedFile, userId ?? 1)
      inputAssetIds = [uploaded.id]
    } else if (editedFile) {
      inputAssetIds = []
    }

    newRecord.inputAssetIds = inputAssetIds
    const result = await submitImg2VideoGeneration({
      modelId: model.id, prompt: newRecord.prompt,
      ratio: newRecord.ratio, resolution: newRecord.resolution, duration: newRecord.duration,
      userId: userId ?? undefined, inputFiles: [], inputAssetIds,
    })

    newRecord.taskId = result.taskId
    saveRecords()
    pollVideo(newRecord, userId ?? undefined).catch(console.error)
  } catch (e: any) {
    newRecord.status = 'error'; newRecord.errorMsg = e.message; saveRecords()
  }
}

// ── 重试 ──────────────────────────────────────────────────
async function retryRecord(record: VideoRecord) {
  if (!record.dbId) {
    return  // 没有 dbId 无法重试
  }
  const newRecord: VideoRecord = {
    id: generateUUID(), createdAt: Date.now(),
    prompt: record.prompt, modelName: record.modelName,
    ratio: record.ratio, resolution: record.resolution, duration: record.duration,
    status: 'generating', mode: record.mode, inputAssetIds: record.inputAssetIds,
  }
  records.value = [newRecord, ...(records.value as VideoRecord[]).filter(r => r.id !== record.id)] as any
  saveRecords()

  try {
    const result = await retryHistory(record.dbId)
    newRecord.taskId = result.task_id
    newRecord.dbId = result.history_id
    saveRecords()
    const userId = getCurrentUserId()
    pollVideo(newRecord, userId ?? undefined).catch(console.error)
  } catch (e: any) {
    newRecord.status = 'error'; newRecord.errorMsg = e.message; saveRecords()
  }
}

// ── 主生成入口 ────────────────────────────────────────────
async function handleGenerate() {
  errorMsg.value = ''
  if (!prompt.value.trim()) { errorMsg.value = '请输入提示词'; return }
  if (generating.value) return  // 防止重复提交
  generating.value = true

  if (modelSource.value === 'api') {
    if (!apiModel.value) { errorMsg.value = '请先在模型管理中添加视频模型'; generating.value = false; return }
    // 图生视频模式必须有输入素材
    if (activeTab.value === 'img2video' && inputFiles.value.length === 0 && selectedAssetIds.value.length === 0) {
      errorMsg.value = '请上传图片/视频或从资产选择'; generating.value = false; return
    }

    const modelName = apiModels.value.find(m => m.id === apiModel.value)?.name || apiModel.value
    const userId = getCurrentUserId()

    // 创建记录并立即插入列表
    const record: VideoRecord = {
      id: generateUUID(), createdAt: Date.now(),
      prompt: prompt.value, modelId: Number(apiModel.value) || undefined, modelName,
      ratio: ratio.value, resolution: resolution.value, duration: duration.value,
      status: 'generating', mode: activeTab.value,
      // 图生视频时记录参考素材信息
      inputAssetIds: activeTab.value === 'img2video' ? [...selectedAssetIds.value] : undefined,
      inputAssetUrls: activeTab.value === 'img2video' ? [
        ...inputPreviews.value.map(p => ({ url: p.url, type: p.type })),
        ...selectedAssetPreviews.value.map(p => ({ url: p.url, type: p.type })),
      ] : undefined,
    }
    records.value.unshift(record)
    saveRecords()
    justSubmitted.value = true
    setTimeout(() => justSubmitted.value = false, 1000)

    try {
      if (activeTab.value === 'img2video') {
        // 图生视频：上传本地文件 + 传入资产预览，后端会处理上传
        const result = await submitImg2VideoGeneration({
          modelId: apiModel.value, prompt: prompt.value,
          ratio: ratio.value, resolution: resolution.value, duration: duration.value,
          userId: userId ?? undefined,
          inputFiles: inputFiles.value,
          inputAssetPreviews: selectedAssetPreviews.value,
          audioFile: audioFile.value ?? undefined,
        })
        record.taskId = result.taskId
        // 后端可能返回上传后的资产 ID
        if (result.inputAssetIds) record.inputAssetIds = result.inputAssetIds
      } else {
        // 文生视频
        const result = await submitVideoGeneration({
          modelId: apiModel.value, prompt: prompt.value,
          ratio: ratio.value, resolution: resolution.value, duration: duration.value,
          userId: userId ?? undefined,
        })
        if (result.taskId) {
          record.taskId = result.taskId
        } else {
          // 极少数情况下同步返回结果
          record.videoUrl = result.videoUrl; record.status = 'done'
          saveRecords(); generating.value = false; return
        }
      }

      saveRecords()
      // 延迟 1.5s 后解除 generating 状态（让用户看到提交成功的反馈）
      setTimeout(() => generating.value = false, 1500)
      pollVideo(record, userId ?? undefined).catch(console.error)
    } catch (e: any) {
      errorMsg.value = 'API 生成失败：' + e.message
      record.status = 'error'; record.errorMsg = e.message
      saveRecords(); generating.value = false
    }
    return
  }

  // 本地视频生成暂未实现
  errorMsg.value = '本地视频生成暂未实现，请使用 API 调用'
  generating.value = false
}

// 下载视频到本地
function downloadVideo(url: string, filename?: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename || url.split('/').pop() || 'video.mp4'
  a.click()
}

// 记录每个视频的收藏状态（key 为记录 ID）
const favoritedVideos = ref<Record<string, boolean>>({})

// 切换某条视频记录的收藏状态
async function toggleVideoFavorite(rec: VideoRecord) {
  if (!rec.outputAssetId) return
  const userStr = localStorage.getItem('user')
  if (!userStr) return
  const user = JSON.parse(userStr)
  const key = rec.id
  const newTag: 0 | 1 = favoritedVideos.value[key] ? 0 : 1
  try {
    await favoriteAsset(rec.outputAssetId, user.id, newTag)
    favoritedVideos.value[key] = newTag === 1
  } catch {
    // 静默失败
  }
}

// 数据库记录转换函数，loadMore 时复用
function mapVideoDbRecord(r: any) {
  return {
    id: String(r.id), dbId: r.id, createdAt: 0,
    prompt: r.prompt || '', modelName: r.model_name || '',
    ratio: '', resolution: '', duration: 0,
    status: (r.status === 'error' ? 'error' : 'done') as 'done' | 'error',
    mode: (r.type === 'img2video' ? 'img2video' : 'txt2video') as 'txt2video' | 'img2video',
    videoUrl: r.output_urls.find((o: any) => o.type === 'video')?.url || r.output_urls[0]?.url,
    outputAssetId: r.output_urls.find((o: any) => o.type === 'video')?.id || r.output_urls[0]?.id,
    inputAssetIds: r.input_asset_ids,
    inputAssetUrls: r.input_asset_urls || [],
    errorMsg: r.status === 'error' ? (r.message || '生成失败') : undefined,
  }
}
const filterVideoDbRecord = (r: any) => r.status !== 'pending' && r.status !== 'processing'

const loadingMore = ref(false)
async function loadMoreHistory() {
  if (loadingMore.value) return
  loadingMore.value = true
  try {
    await loadMoreFromDb(mapVideoDbRecord, filterVideoDbRecord)
  } finally {
    loadingMore.value = false
  }
}

// ── 初始化 ────────────────────────────────────────────────
onMounted(async () => {
  try {
    // 获取视频类型的 API 模型列表
    apiModels.value = await getApiModels('video')
    if (apiModels.value.length > 0) apiModel.value = apiModels.value[0].id
  } catch {}

  // 从数据库加载历史记录
  const userId = await loadFromDb(mapVideoDbRecord, filterVideoDbRecord)

  // 恢复页面刷新前未完成的任务轮询
  const pending = markStaleRecords()
  for (const rec of pending) {
    pollVideo(rec as VideoRecord, userId).catch(console.error)
  }
  saveRecords()
})
</script>


<template>
  <div class="page">
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <div class="layout">
      <!-- ── LEFT PANEL ── -->
      <aside class="left-panel" v-show="!showRecordEditor">
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
              <button class="asset-btn" @click="showAssetPicker = true">
                <span>从资产选择</span>
              </button>
              <label class="local-upload-btn">
                <input type="file" accept="image/*,video/*" multiple @change="(e) => handleFilesChange((e.target as HTMLInputElement).files)" hidden />
                <el-icon><UploadFilled /></el-icon>
                <span>本地上传</span>
              </label>
              <button class="asset-btn" @click="showModelViewer = true">
                <span>3D 截图</span>
              </button>
              <button v-if="inputPreviews.length > 0 || selectedAssetPreviews.length > 0" class="clear-all-btn-small" @click="clearAllInputs">
                清空全部
              </button>
            </div>

            <!-- 音频上传（可选） -->
            <div class="audio-upload-row">
              <template v-if="!audioFile">
                <label class="audio-upload-btn">
                  <input type="file" accept="audio/*" @change="handleAudioChange" hidden />
                  <span>+ 上传音频（可选）</span>
                </label>
              </template>
              <template v-else>
                <div class="audio-file-card">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
                  <span class="audio-file-name">{{ audioFileName }}</span>
                  <button class="audio-remove-btn" @click="removeAudio" title="移除音频">×</button>
                </div>
              </template>
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
        <!-- 编辑模式：编辑器 + 提示词侧边栏 -->
        <template v-if="showRecordEditor">
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
          <div class="edit-sidebar">
            <div class="record-edit-header">
              <span class="record-edit-title">继续生成</span>
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
              <span class="btn-label">继续生成</span>
            </button>
          </div>
        </template>

        <!-- 正常模式：历史记录（始终保留 DOM 防止滚动重置） -->
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
                  <template v-if="rec.inputAssetUrls && rec.inputAssetUrls.length">
                    <button class="input-toggle-btn" @click="toggleInputExpand(rec.id)">
                      参考图
                      <span class="input-toggle-arrow" :class="{ open: expandedInputs.has(rec.id) }">›</span>
                    </button>
                    <template v-if="expandedInputs.has(rec.id)">
                      <template v-for="(a, i) in rec.inputAssetUrls" :key="i">
                        <video v-if="a.type === 'video'" :src="a.url" class="input-panel-thumb" controls />
                        <img v-else :src="a.url" class="input-panel-thumb" @click="previewImage(a.url)" />
                      </template>
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
                      <div class="video-thumb" @click="openVideo(rec.videoUrl, rec.outputAssetId)">
                        <video :src="rec.videoUrl" class="video-player" preload="metadata" />
                        <div class="video-play-icon">▶</div>
                        <button class="download-btn" @click.stop="downloadVideo(rec.videoUrl)" title="下载">
                          <span>⬇</span>
                        </button>
                        <button
                          v-if="rec.outputAssetId"
                          class="favorite-btn"
                          :class="{ favorited: favoritedVideos[rec.id] }"
                          @click.stop="toggleVideoFavorite(rec)"
                          title="收藏"
                        >
                          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                          </svg>
                        </button>
                      </div>
                    </div>
                  </template>
                </RecordCard>
              </div>
              <!-- 分页控件 -->
              <div class="history-pagination">
                <div class="page-size-group">
                  <span class="page-size-label">每页</span>
                  <button
                    v-for="n in [30, 50, 100]" :key="n"
                    class="page-size-btn" :class="{ active: dbPageSize === n }"
                    @click="dbPageSize = (n as 30|50|100); loadFromDb(mapVideoDbRecord, filterVideoDbRecord)"
                  >{{ n }}</button>
                </div>
                <button
                  v-if="hasMoreInDb"
                  class="load-more-btn"
                  :disabled="loadingMore"
                  @click="loadMoreHistory"
                >{{ loadingMore ? '加载中...' : '加载更多' }}</button>
                <span v-else-if="records.length > 0" class="no-more-text">已全部加载</span>
              </div>
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

    <!-- 历史记录图片编辑器（已内联到侧边栏） -->

    <!-- Video Player 弹窗 -->
    <VideoPlayer
      :visible="showVideoPlayer"
      :src="activeVideoUrl"
      :asset-id="activeVideoDbId"
      @close="showVideoPlayer = false"
    />

    <!-- 3D 模型视角截图 -->
    <ModelViewer v-model:visible="showModelViewer" @capture="handleModelCapture" />
  </div>
</template>

<style scoped>
@import '../styles/generation-page.css';

/* ── 视频页专属样式 ── */

.prompt-hint {
  color: rgba(167,139,250,0.6);
  font-size: 10px;
  margin-left: 8px;
}

/* filter group */
.filter-group { display: flex; gap: 6px; flex-wrap: wrap; }

.filter-btn {
  padding: 5px 12px; border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.03);
  color: rgba(255,255,255,0.5); font-size: 11px;
  cursor: pointer; transition: all 0.2s;
}
.filter-btn:hover { border-color: rgba(108,99,255,0.3); background: rgba(108,99,255,0.05); }
.filter-btn.active {
  border-color: rgba(108,99,255,0.6);
  background: rgba(108,99,255,0.2);
  color: rgba(255,255,255,0.9);
}

/* stepper */
.stepper {
  display: flex; align-items: center;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px; overflow: hidden;
  height: 34px; width: 120px; transition: border-color 0.2s;
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

/* upload */
.upload-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.audio-upload-row { margin-top: 8px; }
.audio-upload-btn {
  display: inline-flex; align-items: center; justify-content: center;
  height: 36px; padding: 0 16px; border-radius: 8px;
  border: 1px dashed rgba(255,255,255,0.15);
  background: transparent; color: rgba(255,255,255,0.4);
  font-size: 12px; cursor: pointer; transition: all 0.2s;
}
.audio-upload-btn:hover { border-color: rgba(108,99,255,0.45); color: rgba(108,99,255,0.8); }
.audio-file-card {
  display: inline-flex; align-items: center; gap: 8px;
  height: 36px; padding: 0 10px 0 12px; border-radius: 8px;
  background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.6); font-size: 12px; max-width: 100%;
}
.audio-file-name {
  max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.audio-remove-btn {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%;
  border: none; background: rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.5); font-size: 12px; line-height: 1;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: background 0.2s;
}
.audio-remove-btn:hover { background: rgba(255,80,80,0.3); color: #fff; }

.asset-btn, .local-upload-btn {
  flex: 1; min-width: 120px; height: 60px;
  border-radius: 10px; border: 1px dashed rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.03); color: rgba(255,255,255,0.5);
  font-size: 12px; cursor: pointer;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 6px; transition: all 0.3s;
}
.asset-btn:hover, .local-upload-btn:hover {
  border-color: rgba(108,99,255,0.45);
  background: rgba(108,99,255,0.04);
  color: rgba(255,255,255,0.8);
}

.clear-all-btn-small {
  height: 60px; padding: 0 16px; border-radius: 10px;
  border: 1px solid rgba(248,113,113,0.2);
  background: rgba(248,113,113,0.1); color: #f87171;
  font-size: 12px; cursor: pointer; transition: all 0.2s;
}
.clear-all-btn-small:hover { background: rgba(248,113,113,0.2); border-color: rgba(248,113,113,0.4); }

/* previews grid */
.previews-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 10px; margin-bottom: 12px;
}

.preview-item {
  position: relative; aspect-ratio: 16 / 9;
  border-radius: 8px; overflow: hidden;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(0,0,0,0.3);
}

.preview-media { width: 100%; height: 100%; object-fit: cover; display: block; }

.remove-btn {
  position: absolute; top: 4px; right: 4px;
  width: 20px; height: 20px; border-radius: 50%;
  background: rgba(0,0,0,0.7); border: none;
  color: white; font-size: 14px; line-height: 1; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.remove-btn:hover { background: rgba(220,50,50,0.9); transform: scale(1.1); }

.edit-btn {
  position: absolute; top: 4px; right: 28px;
  width: 20px; height: 20px; border-radius: 50%;
  background: rgba(0,0,0,0.6); border: none; color: white;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.2s; z-index: 2;
}
.edit-btn:hover { background: rgba(108,99,255,0.9); transform: scale(1.1); }

.preview-badge {
  position: absolute; bottom: 4px; left: 4px;
  padding: 2px 6px; border-radius: 4px;
  background: rgba(0,0,0,0.7); color: rgba(255,255,255,0.8); font-size: 10px;
}

/* 视频结果 */
.card-params {
  font-size: 11px; color: rgba(255,255,255,0.35);
  display: flex; gap: 6px;
}

.card-video {
  position: relative; border-radius: 12px; overflow: hidden; background: #000;
  display: inline-block;
}

.video-player {
  width: 100%; max-width: 560px; height: 280px;
  display: block; border-radius: 10px;
  object-fit: contain;
  pointer-events: none;
}

.video-thumb {
  position: relative;
  cursor: pointer;
  border-radius: 10px;
  overflow: hidden;
}
.video-play-icon {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
  color: rgba(255,255,255,0.85);
  background: rgba(0,0,0,0.3);
  transition: background 0.2s;
}
.video-thumb:hover .video-play-icon {
  background: rgba(0,0,0,0.5);
}
.video-thumb:hover .download-btn {
  opacity: 1;
}
.video-thumb:hover .favorite-btn {
  opacity: 1;
}

.favorite-btn {
  position: absolute;
  top: 10px; right: 10px;
  width: 30px; height: 30px;
  border-radius: 50%;
  background: rgba(0,0,0,0.5);
  border: none;
  color: rgba(255,255,255,0.6);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
}
.favorite-btn.favorited {
  opacity: 1;
  color: #f43f5e;
  background: rgba(244,63,94,0.15);
}
.favorite-btn.favorited svg { fill: #f43f5e; stroke: #f43f5e; }
.favorite-btn:hover { transform: scale(1.15); color: #f43f5e; background: rgba(244,63,94,0.2); }

.record-row { align-items: center; }
.record-input-col { width: 240px; }

.history-pagination {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 4px 4px;
  flex-wrap: wrap;
}

.page-size-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.page-size-label {
  font-size: 11px;
  color: rgba(255,255,255,0.35);
}

.page-size-btn {
  padding: 3px 10px;
  border-radius: 5px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.03);
  color: rgba(255,255,255,0.45);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}
.page-size-btn:hover { border-color: rgba(108,99,255,0.3); color: rgba(255,255,255,0.8); }
.page-size-btn.active {
  border-color: rgba(108,99,255,0.6);
  background: rgba(108,99,255,0.2);
  color: rgba(255,255,255,0.9);
}

.load-more-btn {
  padding: 4px 16px;
  border-radius: 6px;
  border: 1px solid rgba(108,99,255,0.4);
  background: rgba(108,99,255,0.12);
  color: rgba(255,255,255,0.7);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.load-more-btn:hover:not(:disabled) { background: rgba(108,99,255,0.25); color: #fff; }
.load-more-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.no-more-text {
  font-size: 11px;
  color: rgba(255,255,255,0.25);
}
</style>

