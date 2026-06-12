<script setup lang="ts">
defineOptions({ name: 'TextToImage' })
// Vue 核心：ref 创建响应式变量，onMounted 页面加载后执行，watch 监听变量变化，computed 计算属性
import { ref, onMounted, watch, computed } from 'vue'
// Element Plus UI 组件：输入框、下拉选择、滑块、数字输入框
import { ElInput, ElSelect, ElOption, ElSlider, ElInputNumber } from 'element-plus'
// Element Plus 图标
import { Refresh, UploadFilled, Close, Setting } from '@element-plus/icons-vue'
// 图片预览组件（全屏查看大图）
import { ElImageViewer } from 'element-plus'
// 资产选择器：从已有素材库中选图
import AssetPicker from '../components/AssetPicker.vue'
// 历史记录卡片：展示每条生成记录
import RecordCard from '../components/RecordCard.vue'
// 图片编辑器：涂抹/裁剪输入图
import ImageEditor from '../components/ImageEditor.vue'
import ModelViewer from '../components/ModelViewer.vue'
// 本地 ComfyUI 接口：获取模型列表、采样器信息、提交任务、上传图片
import { getModels, getKSamplerInfo, submitPrompt, uploadImage, type PromptParams } from '../api/comfyui'
// WebSocket 连接：实时接收本地 ComfyUI 的生成进度和结果图片
import { useComfyWebSocket } from '../composables/useComfyWebSocket'
// 后端 API 接口：获取 API 模型列表、重试历史任务、收藏资产
import { getApiModels, retryHistory, favoriteAsset, type ApiModel } from '../api/apiService'
// 历史记录管理：读写本地存储 + 从数据库加载历史
import { useGenerationHistory } from '../composables/useGenerationHistory'
// 任务轮询：定时查询 API 任务状态，直到完成或失败
import { useTaskPolling } from '../composables/useTaskPolling'
// @提及功能：在提示词输入框中输入 @ 可引用已上传的参考图
import { useAtMention } from '../composables/useAtMention'
// 图片尺寸控制：管理宽高比例、分辨率档位、自定义尺寸
import { useImageSizeControl } from '../composables/useImageSizeControl'
// 历史记录编辑面板：点击历史记录的"继续生图"时打开编辑器
import { useRecordEditor } from '../composables/useRecordEditor'
// 图片生成服务：封装了上传参考图 + 调用 API 的完整流程
import { submitImageGeneration, type InputImage } from '../services/imageGenerationService'
// 工具函数：获取当前登录用户 ID
import { getCurrentUserId } from '../utils/user'
// 工具函数：生成唯一 ID，用于每条生成记录
import { generateUUID } from '../utils/uuid'

// 解构 WebSocket 相关状态和方法：
// clientId - 本次连接的唯一标识，提交任务时传给 ComfyUI
// progress - 当前生成进度 0~100
// generating - 是否正在生成中
// imageUrl - 生成完成后的图片 URL
// connect - 建立 WebSocket 连接
// startGeneration - 开始监听某个任务的进度
const { clientId, progress, generating, imageUrl, connect, startGeneration } = useComfyWebSocket()

// ── 图片预览 ──────────────────────────────────────────────
// 控制全屏图片预览弹窗的显示/隐藏
const showImageViewer = ref(false)
// 当前要预览的图片 URL
const previewImageUrl = ref('')
// 点击图片时调用，打开全屏预览
function previewImage(url: string) {
  previewImageUrl.value = url
  showImageViewer.value = true
}

// ── 生成记录类型 ──────────────────────────────────────────
// 每条生成记录的数据结构定义
interface GenerationRecord {
  id: string                                          // 前端唯一 ID（UUID）
  createdAt: number                                   // 创建时间戳
  prompt: string                                      // 正向提示词
  inputPreviews: string[]                             // 参考图的本地预览 URL（blob: 或 /api/view?...）
  inputAssetUrls?: Array<{ url: string; type: string }> // 参考图的线上 URL（从数据库加载时使用）
  modelName: string                                   // 模型名称（展示用）
  mode: 'api' | 'local'                              // 调用方式：API 还是本地 ComfyUI
  status: 'generating' | 'done' | 'error'            // 当前状态
  progress: number                                    // 进度 0~100（仅本地模式有意义）
  images: string[]                                    // 生成结果图片 URL 列表
  errorMsg?: string                                   // 失败时的错误信息
  taskId?: string                                     // API 任务 ID，用于轮询状态
  isImg2Img?: boolean                                 // 是否是图生图模式
  dbId?: number                                       // 数据库中的记录 ID
  inputAssetIds?: number[]                            // 参考图在资产库中的 ID
  modelId?: number                                    // 模型在数据库中的 ID
  outputAssetIds?: number[]                           // 生成结果在资产库中的 ID（用于收藏）
}

// ── 历史记录 ──────────────────────────────────────────────
// useGenerationHistory 封装了：
// records - 所有历史记录（响应式数组）
// saveRecords - 将 records 持久化到 localStorage
// searchQuery - 搜索关键词
// expandedInputs - 记录哪些条目展开了参考图
// filteredRecords - 按 searchQuery 过滤后的记录列表
// toggleInputExpand - 切换某条记录的参考图展开状态
// deleteRecord - 删除某条记录
// clearAll - 清空所有记录
// loadFromDb - 从后端数据库加载历史记录
// markStaleRecords - 将本地 generating 状态的记录标记为待轮询
const {
  records, saveRecords, searchQuery, expandedInputs, filteredRecords,
  toggleInputExpand, deleteRecord, clearAll, loadFromDb, loadMoreFromDb,
  hasMoreInDb, dbPageSize, markStaleRecords,
} = useGenerationHistory<GenerationRecord>(
  'generation_history',
  'img',
  (r) => ({ images: r.images.filter((img: string) => img.startsWith('http') || img.startsWith('/')) }),
)

// ── 任务轮询 ──────────────────────────────────────────────
// resumeTaskPolling：对某条记录启动轮询，定时查询任务状态
const { resumeTaskPolling } = useTaskPolling<GenerationRecord>(
  () => records.value as GenerationRecord[],
  saveRecords,
)

// 对图片生成任务启动轮询，回调中将结果写入记录
function pollImage(record: GenerationRecord, userId?: number) {
  return resumeTaskPolling(record, userId, (rec, result) => {
    // 将返回的图片列表写入记录（过滤掉空值）
    rec.images = result.images.map((i: any) => i.url).filter(Boolean) as string[]
    // 同时保存资产 ID，用于后续收藏操作
    rec.outputAssetIds = result.images.map((i: any) => i.id).filter(Boolean) as number[]
  })
}

// ── 模型 ──────────────────────────────────────────────────
// API 模型列表（从后端获取，包含 id 和 name）
const apiModels = ref<ApiModel[]>([])
// 当前选中的 API 模型 ID
const apiModel = ref('')
// API 模式下的生成质量：low / medium / high
const apiQuality = ref('medium')
// 本地 ComfyUI 的 checkpoint 模型列表（文件名字符串）
const models = ref<string[]>([])
// 本地 ComfyUI 支持的采样器列表
const samplers = ref<string[]>([])
// 本地 ComfyUI 支持的调度器列表
const schedulers = ref<string[]>([])
// 当前调用方式：local（本地 ComfyUI）或 api（后端 API）
const modelSource = ref<'local' | 'api'>('local')

// ── 表单参数 ──────────────────────────────────────────────
// 当前激活的标签页：文生图 或 图生图
const activeTab = ref<'txt2img' | 'img2img'>('txt2img')
// 计算属性：是否处于图生图模式（避免到处写 activeTab.value === 'img2img'）
const isImg2Img = computed(() => activeTab.value === 'img2img')
// 是否展开高级参数面板（步数、CFG、采样器等）
const showAdvanced = ref(false)
// 页面级错误提示文字
const errorMsg = ref('')
// 防重复提交：点击生成后短暂变为 true，按钮显示"已提交 ✓"
const justSubmitted = ref(false)

// 本地 ComfyUI 的生成参数表单
const form = ref<PromptParams>({
  ckpt_name: '',          // 选中的 checkpoint 模型文件名
  positive_prompt: '',    // 正向提示词
  negative_prompt: '',    // 反向提示词（不想出现的内容）
  width: 512,             // 图片宽度（像素）
  height: 512,            // 图片高度（像素）
  seed: Math.floor(Math.random() * 2 ** 32), // 随机种子，影响生成结果
  steps: 20,              // 采样步数，越高质量越好但越慢
  cfg: 8,                 // CFG Scale，越高越贴近提示词但可能过饱和
  sampler_name: 'dpmpp_2m', // 采样算法
  scheduler: 'karras',   // 噪声调度器
  denoise: 1,             // 降噪强度：1=完全重绘，0=不变（图生图时通常设 0.75）
  batch_size: 1,          // 一次生成几张图
})

// ── 尺寸控制 ──────────────────────────────────────────────
// useImageSizeControl 封装了比例/分辨率的联动逻辑：
// ratios - 可选的宽高比列表（如 1:1、16:9 等）
// resolutions - 可选的分辨率档位（如 512、768、1024）
// activeRatio - 当前选中的比例
// activeResolution - 当前选中的分辨率
// ratioOpen - 比例下拉菜单是否展开
// sizeCustomized - 用户是否手动修改了宽高（此时不高亮任何预设档位）
// setRatio - 选择比例时调用，自动更新宽高
// setResolution - 选择分辨率时调用，自动更新宽高
// startStep / stopStep - 长按宽高步进按钮时的连续增减逻辑
const { ratios, resolutions, activeRatio, activeResolution, ratioOpen, sizeCustomized,
  setRatio, setResolution, startStep, stopStep } =
  useImageSizeControl(
    // 读取当前宽高（供内部计算使用）
    () => ({ width: form.value.width, height: form.value.height }),
    // 写入新宽高（比例/分辨率变化时回调）
    (w, h) => { form.value.width = w; form.value.height = h },
  )

// ── 输入图片 ──────────────────────────────────────────────
// 图生图模式下的参考图列表，每项包含：file（本地文件）、preview（预览 URL）、assetLocation（资产路径）
const inputImages = ref<InputImage[]>([])
// 控制资产选择器弹窗的显示
const showAssetPicker = ref(false)
// 文生图模式下选中的资产路径（暂时保留，实际未使用）
const selectedAssetLocation = ref('')

// 从本地文件添加参考图（最多 4 张）
function addLocalImage(file: File) {
  if (inputImages.value.length >= 4) return
  // URL.createObjectURL 创建临时的 blob: URL 用于预览
  inputImages.value.push({ file, preview: URL.createObjectURL(file), assetLocation: '' })
}

// 从资产库选择图片后的回调
function handleAssetSelect(assets: Array<{ id: number; location: string; asset_type?: string }>) {
  if (activeTab.value === 'img2img') {
    // 图生图模式：API 最多 4 张，本地模式最多 1 张
    const maxImages = modelSource.value === 'api' ? 4 : 1
    for (const asset of assets) {
      if (inputImages.value.length >= maxImages) break
      // 从资产路径中提取文件名，构造 /api/view 预览 URL
      const filename = asset.location.replace(/\\/g, '/').split('/').pop()!
      inputImages.value.push({
        file: null,
        preview: `/api/view?filename=${encodeURIComponent(filename)}&type=output`,
        assetLocation: asset.location,
      })
    }
  } else {
    // 文生图模式：只记录第一个资产的路径
    if (assets.length > 0) selectedAssetLocation.value = assets[0].location
  }
}

// ── @mention ──────────────────────────────────────────────
// 提示词输入框的 ref，用于 @mention 功能定位光标
const promptInputRef = ref<InstanceType<typeof ElInput> | null>(null)
// useAtMention 封装了在提示词中输入 @ 后弹出图片选择下拉的逻辑：
// atMentionActive - 下拉是否显示
// atMentionIndex - 当前高亮的选项索引（键盘上下键控制）
// onPromptKeyup / onPromptKeydown - 绑定到输入框的键盘事件处理
// insertMention - 选中某张图后插入 @图N 文本
const { atMentionActive, atMentionIndex, onPromptKeyup, onPromptKeydown, insertMention } =
  useAtMention(
    () => form.value.positive_prompt,                                          // 读取当前提示词
    (v) => { form.value.positive_prompt = v },                                 // 写入提示词
    () => inputImages.value.map(img => ({ url: img.preview, type: 'image' as const })), // 可选的图片列表
    promptInputRef,
  )

// ── 图片编辑器（输入图） ──────────────────────────────────
// 控制输入图编辑器弹窗的显示
const showEditor = ref(false)
// 当前正在编辑的参考图索引（对应 inputImages 数组）
const editingIndex = ref(-1)
// 资产选择器的目标索引（-1 表示添加新图，>=0 表示替换某张）
const assetPickerTargetIndex = ref(-1)

// 3D 模型视角截图
const showModelViewer = ref(false)
function handleModelCapture(file: File) {
  if (inputImages.value.length >= 4) return
  inputImages.value.push({ file, preview: URL.createObjectURL(file), assetLocation: '' })
}

// 打开某张参考图的编辑器
function openEditor(idx: number) {
  editingIndex.value = idx
  showEditor.value = true
}

// 编辑器确认后的回调：用编辑后的文件替换原来的参考图
function onEditorConfirm(file: File) {
  const idx = editingIndex.value
  if (idx >= 0 && idx < inputImages.value.length) {
    inputImages.value[idx] = { file, preview: URL.createObjectURL(file), assetLocation: '' }
  }
  showEditor.value = false
}

// ── 历史记录编辑面板 ──────────────────────────────────────
// 历史记录内联编辑器的 ref（用于获取编辑后的图片数据）
const inlineEditorRef = ref<InstanceType<typeof ImageEditor> | null>(null)
// useRecordEditor 封装了点击历史记录"继续生图"时的编辑面板逻辑：
// showRecordEditor - 是否显示编辑面板（显示时左侧面板隐藏）
// editingRecordId - 当前编辑的记录 ID
// recordEditorPrompt - 编辑面板中的提示词（可修改）
// recordEditorImages - 原始参考图 URL 列表
// recordEditorEditedPreview - 编辑后的图片预览 URL
// recordEditorEditingSrc - 当前正在编辑的图片源 URL
// showRecordImageEditor - 是否显示图片编辑器子面板
// openEditor - 打开某条记录的编辑面板
// onImageEditorConfirm / onImageEditorCancel - 图片编辑器的确认/取消
// closeEditor - 关闭编辑面板
// getEditedFile - 获取编辑后的 File 对象（如果有涂抹修改）
const {
  showRecordEditor, editingRecordId, recordEditorPrompt, recordEditorImages,
  recordEditorEditedPreview, recordEditorEditingSrc, showRecordImageEditor,
  openEditor: openRecordEditor, onImageEditorConfirm: onRecordImageEditorConfirm,
  onImageEditorCancel: onRecordImageEditorCancel, closeEditor: closeRecordEditor, getEditedFile,
} = useRecordEditor(inlineEditorRef)

// 点击历史记录卡片的"继续生图"按钮
function handleRecordEdit(id: string) {
  const rec = (records.value as GenerationRecord[]).find(r => r.id === id)
  // 只有已完成的记录才能继续生图
  if (!rec || rec.status !== 'done') return
  openRecordEditor(rec)
}

// 在编辑面板中点击"继续生图"按钮
async function generateFromEdit() {
  if (!apiModel.value) { errorMsg.value = '请先选择 API 模型'; return }
  closeRecordEditor()

  // 如果用户在编辑器中涂抹了图片，获取修改后的 File；否则使用原始图片 URL
  const editedFile = await getEditedFile()
  const src = editedFile ? URL.createObjectURL(editedFile) : recordEditorImages.value[0]
  if (!src) return

  // 创建新的生成记录并插入到列表最前面
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
// 调用后端 API 执行图片生成，支持文生图和图生图
// recordId: 对应的历史记录 ID
// img2img: 是否是图生图模式
// snapshotImages: 参考图快照（提交时的副本，防止用户后续修改影响本次任务）
async function runApiGeneration(recordId: string, img2img: boolean, snapshotImages: InputImage[]) {
  const getRecord = () => (records.value as GenerationRecord[]).find(r => r.id === recordId)
  const rec = getRecord()
  if (!rec) return

  try {
    const userId = getCurrentUserId()
    // submitImageGeneration 会上传参考图、调用 API、返回 taskId 或直接返回图片
    const result = await submitImageGeneration({
      modelId: rec.modelId,
      prompt: rec.prompt,
      aspect_ratio: activeRatio.value.label,  // 当前选中的宽高比（如 "1:1"、"16:9"）
      quality: apiQuality.value,
      batchSize: form.value.batch_size,
      img2img,
      inputImages: snapshotImages,
      userId: userId ?? undefined,
    })

    if (result.taskId) {
      // 异步任务：保存 taskId 后开始轮询
      rec.taskId = result.taskId
      saveRecords()
      pollImage(rec, userId ?? undefined).catch(console.error)
    } else {
      // 同步返回（极少数情况）：直接写入结果
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

// 重试某条失败的历史记录（通过数据库 ID 让后端重新执行）
async function retryRecord(record: GenerationRecord) {
  if (!record.dbId) {
    return  // 没有 dbId 说明是本地记录，无法重试
  }
  // 创建新记录替换旧记录（旧记录从列表中移除）
  const newRecord: GenerationRecord = {
    id: generateUUID(), createdAt: Date.now(),
    mode: record.mode, prompt: record.prompt, modelName: record.modelName,
    status: 'generating', inputPreviews: record.inputPreviews,
    progress: 0, images: [],  isImg2Img: record.isImg2Img,
  }
  records.value = [newRecord, ...(records.value as GenerationRecord[]).filter(r => r.id !== record.id)] as any
  saveRecords()

  try {
    // 调用后端重试接口，返回新的 task_id 和 history_id
    const result = await retryHistory(record.dbId)
    newRecord.taskId = result.task_id
    newRecord.dbId = result.history_id
    saveRecords()
    const userId = getCurrentUserId()
    pollImage(newRecord, userId ?? undefined).catch(console.error)
  } catch (e: any) {
    newRecord.status = 'error'; newRecord.errorMsg = e.message; saveRecords()
  }
}

// ── 主生成入口 ────────────────────────────────────────────
// 点击"开始生成"按钮时调用，根据 modelSource 分别走 API 或本地 ComfyUI 流程
async function handleGenerate() {
  errorMsg.value = ''
  // 获取模型显示名称（API 模式从列表中查，本地模式直接用文件名）
  const modelName = modelSource.value === 'api'
    ? (apiModels.value.find(m => m.id === apiModel.value)?.name || apiModel.value)
    : form.value.ckpt_name
  // 快照当前参考图的预览 URL（用于记录展示）
  const inputPreviews = inputImages.value.map(img => img.preview)

  if (modelSource.value === 'api') {
    if (!apiModel.value) { errorMsg.value = '请先在模型管理中添加 API 模型'; return }
    if (isImg2Img.value && inputImages.value.length === 0) {
      errorMsg.value = '请先上传或选择参考图片'; return
    }
    // 创建生成记录并立即插入列表（用户能立刻看到"生成中"状态）
    const record: GenerationRecord = {
      id: generateUUID(), createdAt: Date.now(),
      prompt: form.value.positive_prompt, inputPreviews, modelName,
      modelId: Number(apiModel.value) || undefined,
      mode: 'api', status: 'generating', progress: 0, images: [],
      isImg2Img: isImg2Img.value,
    }
    records.value.unshift(record)
    saveRecords()
    // 短暂禁用按钮防止重复提交
    justSubmitted.value = true
    setTimeout(() => justSubmitted.value = false, 1000)
    // 传入参考图快照（[...inputImages.value] 是浅拷贝，防止后续修改影响本次任务）
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
        // 本地文件：先上传到 ComfyUI，获取服务器端文件名
        form.value.input_image = await uploadImage(firstImg.file)
      } else if (firstImg.assetLocation) {
        // 资产库文件：直接使用资产路径
        form.value.input_image = firstImg.assetLocation
      } else {
        record.status = 'error'; record.errorMsg = '请先上传或选择参考图片'; saveRecords(); return
      }
    } else {
      form.value.input_image = undefined  // 文生图模式不需要输入图
    }
    // 提交任务到 ComfyUI，返回 prompt_id
    const res = await submitPrompt(form.value, clientId)
    // 开始通过 WebSocket 监听该任务的进度
    startGeneration(res.prompt_id)
  } catch {
    errorMsg.value = '提交失败，请检查 ComfyUI 后端'
    const rec = (records.value as GenerationRecord[]).find(r => r.mode === 'local' && r.status === 'generating')
    if (rec) { rec.status = 'error'; rec.errorMsg = '提交失败'; saveRecords() }
    generating.value = false
  }
}

// 下载图片到本地
function downloadImage(url: string, filename?: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename || url.split('/').pop() || 'image.png'
  a.click()
}

// 切换某张结果图的收藏状态
async function toggleImageFavorite(rec: GenerationRecord, index: number) {
  const assetId = rec.outputAssetIds?.[index]
  if (!assetId) return
  const userStr = localStorage.getItem('user')
  if (!userStr) return
  const user = JSON.parse(userStr)
  // 读取当前收藏状态（1=已收藏，0=未收藏）
  const currentTag = (rec as any)._favoritedImages?.[index] ? 1 : 0
  const newTag: 0 | 1 = currentTag === 1 ? 0 : 1
  try {
    await favoriteAsset(assetId, user.id, newTag)
    // 更新本地状态（_favoritedImages 是运行时附加的属性，不持久化）
    if (!(rec as any)._favoritedImages) (rec as any)._favoritedImages = {}
    ;(rec as any)._favoritedImages[index] = newTag === 1
  } catch {
    // 静默失败
  }
}

// ── 本地模式 WebSocket 进度 ───────────────────────────────
// 监听 WebSocket 推送的进度值，更新对应记录的进度条
watch(progress, (val) => {
  const rec = (records.value as GenerationRecord[]).find(r => r.mode === 'local' && r.status === 'generating')
  if (rec) rec.progress = val
})

// 监听 WebSocket 推送的结果图片 URL，生成完成时更新记录状态
watch(imageUrl, (url) => {
  if (!url) return
  const rec = (records.value as GenerationRecord[]).find(r => r.mode === 'local' && r.status === 'generating')
  if (rec) { rec.images = [url]; rec.status = 'done'; saveRecords() }
})

// 监听生成状态：如果 generating 变为 false 但记录还没有图片，说明超时或失败
watch(generating, (val) => {
  if (!val) {
    const rec = (records.value as GenerationRecord[]).find(r => r.mode === 'local' && r.status === 'generating')
    if (rec && rec.images.length === 0) { rec.status = 'error'; rec.errorMsg = '生成超时或失败'; saveRecords() }
  }
})

// 切换到图生图时自动将降噪强度设为 0.75（保留参考图特征），切回文生图时恢复 1（完全重绘）
watch(isImg2Img, (val) => { form.value.denoise = val ? 0.75 : 1 })

// 数据库记录转换函数，loadMore 时复用
function mapImgDbRecord(r: any) {
  return {
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
    outputAssetIds: r.output_urls.map((o: any) => o.id).filter(Boolean),
    inputAssetIds: r.input_asset_ids,
    errorMsg: r.status === 'error' ? (r.message || '生成失败') : undefined,
  }
}
const filterImgDbRecord = (r: any) => r.status !== 'pending' && r.status !== 'processing'

const loadingMore = ref(false)
async function loadMoreHistory() {
  if (loadingMore.value) return
  loadingMore.value = true
  try {
    await loadMoreFromDb(mapImgDbRecord, filterImgDbRecord)
  } finally {
    loadingMore.value = false
  }
}

// ── 初始化 ────────────────────────────────────────────────
onMounted(async () => {
  // 建立 WebSocket 连接，用于接收本地 ComfyUI 的实时进度
  connect()

  try {
    // 并行请求本地 ComfyUI 的模型列表和采样器信息
    const [modelList, ksInfo] = await Promise.all([getModels(), getKSamplerInfo()])
    models.value = modelList
    samplers.value = ksInfo.samplers
    schedulers.value = ksInfo.schedulers
    if (modelList.length > 0) form.value.ckpt_name = modelList[0]  // 默认选第一个模型
    else errorMsg.value = '未找到任何 checkpoint 模型'
  } catch {
    errorMsg.value = '无法连接 ComfyUI 后端（默认 127.0.0.1:8188）'
  }

  try {
    // 获取后端 API 模型列表（type='image' 只返回图片模型）
    apiModels.value = await getApiModels('image')
    if (apiModels.value.length > 0) apiModel.value = apiModels.value[0].id  // 默认选第一个
  } catch {}

  // 从数据库加载历史记录，将后端数据格式转换为前端 GenerationRecord 格式
  const userId = await loadFromDb(mapImgDbRecord, filterImgDbRecord)

  // 将页面刷新前处于 generating 状态的 API 记录标记为待轮询，并恢复轮询
  const pending = markStaleRecords('local')
  for (const rec of pending) {
    pollImage(rec as GenerationRecord, userId).catch(console.error)
  }

  // 本地 ComfyUI 的 generating 记录在刷新后无法恢复，直接标记为失败
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
              <button class="asset-btn" @click="showModelViewer = true">
                <span>3D 截图</span>
              </button>
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

          <!-- resolution：本地模式显示像素档位，API 模式显示清晰度档位 -->
          <div class="row-item">
            <span class="row-label">清晰度</span>
            <div class="source-toggle">
              <template v-if="modelSource === 'local'">
                <button
                  v-for="r in resolutions" :key="r.label"
                  :class="{ active: !sizeCustomized && activeResolution.label === r.label }"
                  @click="setResolution(r)"
                >{{ r.label }}</button>
              </template>
              <template v-else>
                <button
                  v-for="q in ['low', 'medium', 'high']" :key="q"
                  :class="{ active: apiQuality === q }"
                  @click="apiQuality = q"
                >{{ q }}</button>
              </template>
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

          <!-- size preview：仅本地模式显示像素数 -->
          <div v-if="modelSource === 'local'" class="size-preview">{{ form.width }} × {{ form.height }}</div>

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
                        <button
                          v-if="rec.outputAssetIds?.[i]"
                          class="favorite-btn"
                          :class="{ favorited: (rec as any)._favoritedImages?.[i] }"
                          @click.stop="toggleImageFavorite(rec as any, i)"
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
                    @click="dbPageSize = (n as 30|50|100); loadFromDb(mapImgDbRecord, filterImgDbRecord)"
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

    <!-- 3D 模型视角截图 -->
    <ModelViewer v-model:visible="showModelViewer" @capture="handleModelCapture" />
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
.card-image-wrap:hover .favorite-btn { opacity: 1; }

.favorite-btn {
  position: absolute;
  top: 8px; right: 8px;
  width: 28px; height: 28px;
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

/* 进度 */
.loading-text { font-size: 12px; color: rgba(255,255,255,0.35); }

.record-row.editing {
  outline: 1px solid rgba(108,99,255,0.3);
  border-radius: 16px;
}

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

