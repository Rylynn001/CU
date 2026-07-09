<script setup lang="ts">
defineOptions({ name: 'TextToVideo' })
// Vue 鏍稿績
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
// Element Plus UI 缁勪欢
import { ElInput, ElSelect, ElOption } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
// 璧勪骇閫夋嫨鍣ㄥ脊绐?
import AssetSidebar from '../components/AssetSidebar.vue'
// 瑙嗛鎾斁鍣ㄥ脊绐楋紙鐐瑰嚮鍘嗗彶璁板綍涓殑瑙嗛鏃舵墦寮€锛?import VideoPlayer from '../components/VideoPlayer.vue'
// 鍘嗗彶璁板綍鍗＄墖
import RecordCard from '../components/RecordCard.vue'
// 鍥剧墖缂栬緫鍣紙鍥剧敓瑙嗛鏃跺彲浠ユ秱鎶瑰弬鑰冨浘锛?
import ImageEditor from '../components/ImageEditor.vue'
import ModelViewer from '../components/ModelViewer.vue'
import FavoriteHeart from '../components/FavoriteHeart.vue'
import ProjectManager from '../components/ProjectManager.vue'
// 鍚庣 API 鎺ュ彛
import { getApiModels, retryHistory, favoriteAsset, type ApiModel } from '../api/apiService'
// 鍘嗗彶璁板綍绠＄悊
import { useGenerationHistory } from '../composables/useGenerationHistory'
// 浠诲姟杞
import { useTaskPolling } from '../composables/useTaskPolling'
// @鎻愬強鍔熻兘
import { useAtMention } from '../composables/useAtMention'
// 鍘嗗彶璁板綍缂栬緫闈㈡澘
import { useRecordEditor } from '../composables/useRecordEditor'
// 杈撳叆濯掍綋绠＄悊锛氱粺涓€绠＄悊鏈湴涓婁紶鏂囦欢鍜岃祫浜у簱閫夋嫨鐨勫浘鐗?瑙嗛
import { useInputMedia } from '../composables/useInputMedia'
// 璺ㄩ〉闈㈠畾浣嶅巻鍙茶褰曪細璧勪骇搴撳彸閿?瀹氫綅鍘嗗彶璁板綍"鍚庯紝鍦ㄨ繖閲屾秷璐瑰苟婊氬姩+楂樹寒
import { useLocateHistory } from '../composables/useLocateHistory'
// 瑙嗛鐢熸垚鏈嶅姟锛氭枃鐢熻棰?鍜?鍥剧敓瑙嗛 鐨?API 璋冪敤灏佽
import { submitVideoGeneration, submitImg2VideoGeneration } from '../services/videoGenerationService'
import { getCurrentUserId } from '../utils/user'
import { generateUUID } from '../utils/uuid'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

const router = useRouter()

// 鈹€鈹€ 鐢熸垚璁板綍绫诲瀷 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
interface VideoRecord {
  id: string                                            // 鍓嶇鍞竴 ID
  createdAt: number                                     // 鍒涘缓鏃堕棿鎴?
  prompt: string                                        // 鎻愮ず璇?
  modelName: string                                     // 妯″瀷鍚嶇О
  ratio: string                                         // 瀹介珮姣旓紙濡?"16:9"锛?
  resolution: string                                    // 鍒嗚鲸鐜囷紙濡?"720p"锛?
  duration: number                                      // 瑙嗛鏃堕暱锛堢锛?
  status: 'generating' | 'done' | 'error'              // 褰撳墠鐘舵€?
  videoUrl?: string                                     // 鐢熸垚缁撴灉瑙嗛 URL
  errorMsg?: string                                     // 澶辫触鏃剁殑閿欒淇℃伅
  taskId?: string                                       // API 浠诲姟 ID锛岀敤浜庤疆璇?
  mode: 'txt2video' | 'img2video'                      // 鏂囩敓瑙嗛 鎴?鍥剧敓瑙嗛
  inputAssetIds?: number[]                              // 鍙傝€冪礌鏉愬湪璧勪骇搴撲腑鐨?ID
  inputAssetUrls?: Array<{ url: string; type: string }> // 鍙傝€冪礌鏉愮殑绾夸笂 URL锛堝睍绀虹敤锛?
  dbId?: number                                         // 鏁版嵁搴撹褰?ID
  modelId?: number                                      // 妯″瀷鏁版嵁搴?ID
  outputAssetId?: number                                // 杈撳嚭瑙嗛鍦ㄨ祫浜у簱涓殑 ID锛堢敤浜庢敹钘忥級
}

// 鈹€鈹€ 鍘嗗彶璁板綍 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const {
  records, saveRecords, searchQuery, expandedInputs, filteredRecords,
  toggleInputExpand, deleteRecord, clearAll, loadFromDb, loadMoreFromDb,
  hasMoreInDb, dbPageSize, markStaleRecords,
} = useGenerationHistory<VideoRecord>('video_generation_history', 'video',
  (r) => ({
    // blob: URL 鍦ㄩ〉闈㈠埛鏂板悗澶辨晥锛屼繚瀛樻椂杩囨护鎺夛紝涓嬫浠庢暟鎹簱閲嶆柊鍔犺浇绾夸笂 URL
    inputAssetUrls: r.inputAssetUrls?.filter(a => !a.url.startsWith('blob:')),
  }),
)

// 鈹€鈹€ 浠诲姟杞 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const { resumeTaskPolling } = useTaskPolling<VideoRecord>(
  () => records.value as VideoRecord[],
  saveRecords,
)

// 瀵硅棰戠敓鎴愪换鍔″惎鍔ㄨ疆璇紝鍥炶皟涓皢缁撴灉鍐欏叆璁板綍
function pollVideo(record: VideoRecord, userId?: number) {
  return resumeTaskPolling(record, userId, (rec, result) => {
    // 浠庤繑鍥炵殑 images 鏁扮粍涓壘鍒拌棰戠被鍨嬬殑鏉＄洰
    const videoItem = result.images.find((i: any) => i.url)
    rec.videoUrl = videoItem?.url || ''
    if (videoItem?.id) rec.outputAssetId = videoItem.id
    // 濡傛灉鍚庣杩斿洖浜嗗弬鑰冪礌鏉愮殑绾夸笂 URL锛屾洿鏂板埌璁板綍涓紙鐢ㄤ簬灞曠ず锛?
    if ((result as any).inputAssetUrls?.length) {
      rec.inputAssetUrls = (result as any).inputAssetUrls
    }
  }, 'video')  // 'video' 鍛婅瘔杞鍣ㄨ繖鏄棰戜换鍔?
}

// 鈹€鈹€ 妯″瀷 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const apiModels = ref<ApiModel[]>([])
const apiModel = ref('')
// 瑙嗛椤甸粯璁や娇鐢?API 妯″紡锛堟湰鍦拌棰戠敓鎴愭殏鏈疄鐜帮級
const modelSource = ref<'local' | 'api'>('api')
// 褰撳墠鏍囩椤碉細鏂囩敓瑙嗛 鎴?鍥剧敓瑙嗛
const activeTab = ref<'txt2video' | 'img2video'>('txt2video')
const isImg2Video = computed(() => activeTab.value === 'img2video')

// 鈹€鈹€ 鍙傛暟 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const prompt = ref('')
const generating = ref(false)
const errorMsg = ref('')
// 闃查噸澶嶆彁浜ゆ爣蹇?
const justSubmitted = ref(false)
// 瑙嗛瀹介珮姣?
const ratio = ref('16:9')
// 瑙嗛鍒嗚鲸鐜?
const resolution = ref('720p')
// 瑙嗛鏃堕暱锛堢锛?
const duration = ref(8)

// 瀹介珮姣旈€夐」鍒楄〃
const ratioOptions = [
  { label: '16:9', value: '16:9' },
  { label: '4:3', value: '4:3' },
  { label: '1:1', value: '1:1' },
  { label: '3:4', value: '3:4' },
  { label: '9:16', value: '9:16' },
  { label: '21:9', value: '21:9' },
  { label: 'adaptive', value: 'adaptive' },  // 鑷€傚簲锛氱敱妯″瀷鏍规嵁鍙傝€冨浘鍐冲畾
]

// 鍒嗚鲸鐜囬€夐」鍒楄〃
const resolutionOptions = [
  { label: '480p', value: '480p' },
  { label: '720p', value: '720p' },
  { label: '1080p', value: '1080p' },
]

// 鈹€鈹€ 杈撳叆濯掍綋 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

// 闊抽鏂囦欢锛堝彲閫夛級
const audioFile = ref<File | null>(null)
const audioFileName = computed(() => audioFile.value?.name ?? '')
function handleAudioChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) audioFile.value = file
}
function removeAudio() {
  audioFile.value = null
}

// 3D 妯″瀷瑙嗚鎴浘
const showModelViewer = ref(false)
function handleModelCapture(file: File) {
  inputFiles.value.push(file)
  inputPreviews.value.push({ url: URL.createObjectURL(file), type: 'image' })
}
// useInputMedia 缁熶竴绠＄悊鍥剧敓瑙嗛鐨勮緭鍏ョ礌鏉愶細
// inputFiles - 鏈湴涓婁紶鐨勬枃浠跺垪琛?
// inputPreviews - 鏈湴鏂囦欢鐨勯瑙堜俊鎭紙url + type锛?
// selectedAssetIds - 浠庤祫浜у簱閫夋嫨鐨勭礌鏉?ID 鍒楄〃
// selectedAssetPreviews - 璧勪骇搴撶礌鏉愮殑棰勮淇℃伅锛坲rl + type + id锛?
// allMediaItems - 鍚堝苟鍚庣殑鎵€鏈夌礌鏉愶紙鐢ㄤ簬 @mention 涓嬫媺锛?
// handleFilesChange - 澶勭悊鏂囦欢閫夋嫨浜嬩欢锛堟敮鎸佸閫夛紝鑷姩鏍￠獙鏁伴噺涓婇檺锛?
// removeFile / removeAsset - 鍒犻櫎鏌愪釜鏈湴鏂囦欢 / 璧勪骇
// clearAllInputs - 娓呯┖鎵€鏈夎緭鍏ョ礌鏉?
// handleAssetSelect - 璧勪骇閫夋嫨鍣ㄥ洖璋?
// replaceFile / replaceAssetWithFile - 缂栬緫鍥剧墖鍚庢浛鎹㈠師绱犳潗
const {
  inputFiles, inputPreviews, selectedAssetIds, selectedAssetPreviews, allMediaItems,
  handleFilesChange, removeFile, removeAsset, clearAllInputs, handleAssetSelect,
  replaceFile, replaceAssetWithFile,
} = useInputMedia((msg) => { errorMsg.value = msg })

// 鈹€鈹€ @mention 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const promptInputRef = ref<InstanceType<typeof ElInput> | null>(null)
const { atMentionActive, atMentionIndex, onPromptKeyup, onPromptKeydown, insertMention } =
  useAtMention(
    () => prompt.value,
    (v) => { prompt.value = v },
    () => allMediaItems.value,  // @mention 鍙紩鐢ㄦ墍鏈夊凡涓婁紶鐨勫浘鐗囧拰瑙嗛
    promptInputRef,
  )

// 鈹€鈹€ 鍥剧墖棰勮 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const showImageViewer = ref(false)
const previewImageList = ref<string[]>([])
const currentPreviewIndex = ref(0)
const imageScale = ref(1)
const MIN_SCALE = 0.5
const MAX_SCALE = 5

function previewImage(url: string, imageList?: string[]) {
  if (imageList && imageList.length > 0) {
    previewImageList.value = imageList
    const idx = imageList.indexOf(url)
    currentPreviewIndex.value = idx >= 0 ? idx : 0
  } else {
    previewImageList.value = [url]
    currentPreviewIndex.value = 0
  }
  imageScale.value = 1
  showImageViewer.value = true
}

const currentPreviewUrl = computed(() => {
  return previewImageList.value[currentPreviewIndex.value] || ''
})

function handleImageWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  imageScale.value = Math.max(MIN_SCALE, Math.min(MAX_SCALE, imageScale.value + delta))
}

function goToPrevImage() {
  if (previewImageList.value.length === 0) return
  currentPreviewIndex.value = (currentPreviewIndex.value - 1 + previewImageList.value.length) % previewImageList.value.length
  imageScale.value = 1
}

function goToNextImage() {
  if (previewImageList.value.length === 0) return
  currentPreviewIndex.value = (currentPreviewIndex.value + 1) % previewImageList.value.length
  imageScale.value = 1
}

function handleImageKeydown(e: KeyboardEvent) {
  if (!showImageViewer.value) return

  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    goToPrevImage()
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    goToNextImage()
  } else if (e.key === 'Escape') {
    e.preventDefault()
    showImageViewer.value = false
  }
}

// 鈹€鈹€ 瑙嗛鎾斁鍣ㄥ脊绐?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
// 鎺у埗瑙嗛鎾斁鍣ㄥ脊绐楃殑鏄剧ず
const showVideoPlayer = ref(false)
// 褰撳墠鎾斁鐨勮棰?URL
const activeVideoUrl = ref('')
// 褰撳墠鎾斁瑙嗛瀵瑰簲鐨勮祫浜?ID锛堢敤浜庢敹钘忕瓑鎿嶄綔锛?
const activeVideoDbId = ref<number | undefined>(undefined)

// 鐐瑰嚮鍘嗗彶璁板綍涓殑瑙嗛缂╃暐鍥炬椂鎵撳紑鎾斁鍣?
function openVideo(url: string, dbId?: number) {
  activeVideoUrl.value = url
  activeVideoDbId.value = dbId
  showVideoPlayer.value = true
}

// 鈹€鈹€ 鍥剧墖缂栬緫鍣紙杈撳叆绱犳潗锛?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
// 鎺у埗杈撳叆绱犳潗缂栬緫鍣ㄥ脊绐?
const showEditor = ref(false)
// 褰撳墠缂栬緫鐨勭礌鏉愭潵婧愶細鏈湴鏂囦欢 鎴?璧勪骇搴?
const editingSource = ref<'file' | 'asset'>('file')
// 褰撳墠缂栬緫鐨勬湰鍦版枃浠剁储寮?
const editingFileIndex = ref(-1)
// 褰撳墠缂栬緫鐨勮祫浜х储寮?
const editingAssetIndex = ref(-1)

function openLocalEditor(index: number) {
  editingSource.value = 'file'; editingFileIndex.value = index; showEditor.value = true
}
function openAssetEditor(index: number) {
  editingSource.value = 'asset'; editingAssetIndex.value = index; showEditor.value = true
}
function onEditorCancel() { showEditor.value = false }

// 缂栬緫鍣ㄧ‘璁ゅ悗锛屾牴鎹潵婧愭浛鎹㈠搴旂殑绱犳潗
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

// 鈹€鈹€ 鍘嗗彶璁板綍缂栬緫闈㈡澘 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const inlineEditorRef = ref<InstanceType<typeof ImageEditor> | null>(null)
const {
  showRecordEditor, recordEditorPrompt,
  recordEditorEditedPreview, recordEditorEditingSrc, showRecordImageEditor,
  openEditor: openRecordEditor, onImageEditorConfirm: onRecordImageEditorConfirm,
  onImageEditorCancel: onRecordImageEditorCancel, closeEditor: closeRecordEditor, getEditedFile,
} = useRecordEditor(inlineEditorRef)

// 鐐瑰嚮鍘嗗彶璁板綍鍗＄墖鐨?缁х画鐢熸垚"鎸夐挳
function handleRecordEdit(id: string) {
  const rec = (records.value as VideoRecord[]).find(r => r.id === id)
  if (!rec || rec.status !== 'done') return
  openRecordEditor(rec)
}

// 鍦ㄧ紪杈戦潰鏉夸腑鐐瑰嚮"缁х画鐢熸垚"鎸夐挳锛堝浘鐢熻棰戞ā寮忥紝浣跨敤缂栬緫鍚庣殑鍥剧墖閲嶆柊鐢熸垚锛?
async function generateFromEdit() {
  if (!apiModel.value) { errorMsg.value = '请先选择 API 模型'; return }
  closeRecordEditor()

  const model = apiModels.value.find(m => m.id === apiModel.value)
  if (!model) { errorMsg.value = '找不到对应模型'; return }

  const editedFile = await getEditedFile()
  const userId = getCurrentUserId()

  // 鍒涘缓鏂拌褰?
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
      // 灏嗙紪杈戝悗鐨勫浘鐗囦笂浼犲埌璧勪骇搴擄紝鑾峰彇璧勪骇 ID
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

// 鈹€鈹€ 閲嶈瘯 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
async function retryRecord(record: VideoRecord) {
  if (!record.dbId) {
    return  // 娌℃湁 dbId 鏃犳硶閲嶈瘯
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

// 鈹€鈹€ 涓荤敓鎴愬叆鍙?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
async function handleGenerate() {
  errorMsg.value = ''
  if (!prompt.value.trim()) { errorMsg.value = '请输入提示词'; return }
  if (generating.value) return  // 闃叉閲嶅鎻愪氦
  generating.value = true

  if (modelSource.value === 'api') {
    if (!apiModel.value) { errorMsg.value = '请先在模型管理中添加视频模型'; generating.value = false; return }
    // 鍥剧敓瑙嗛妯″紡蹇呴』鏈夎緭鍏ョ礌鏉?
    if (activeTab.value === 'img2video' && inputFiles.value.length === 0 && selectedAssetIds.value.length === 0) {
      errorMsg.value = '请上传图片、视频，或从资产中选择'; generating.value = false; return
    }

    const modelName = apiModels.value.find(m => m.id === apiModel.value)?.name || apiModel.value
    const userId = getCurrentUserId()

    // 鍒涘缓璁板綍骞剁珛鍗虫彃鍏ュ垪琛?
    const record: VideoRecord = {
      id: generateUUID(), createdAt: Date.now(),
      prompt: prompt.value, modelId: Number(apiModel.value) || undefined, modelName,
      ratio: ratio.value, resolution: resolution.value, duration: duration.value,
      status: 'generating', mode: activeTab.value,
      // 鍥剧敓瑙嗛鏃惰褰曞弬鑰冪礌鏉愪俊鎭?
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
        // 鍥剧敓瑙嗛锛氫笂浼犳湰鍦版枃浠?+ 浼犲叆璧勪骇棰勮锛屽悗绔細澶勭悊涓婁紶
        const result = await submitImg2VideoGeneration({
          modelId: apiModel.value, prompt: prompt.value,
          ratio: ratio.value, resolution: resolution.value, duration: duration.value,
          userId: userId ?? undefined,
          inputFiles: inputFiles.value,
          inputAssetPreviews: selectedAssetPreviews.value,
          audioFile: audioFile.value ?? undefined,
        })
        record.taskId = result.taskId
        // 鍚庣鍙兘杩斿洖涓婁紶鍚庣殑璧勪骇 ID
        if (result.inputAssetIds) record.inputAssetIds = result.inputAssetIds
      } else {
        // 鏂囩敓瑙嗛
        const result = await submitVideoGeneration({
          modelId: apiModel.value, prompt: prompt.value,
          ratio: ratio.value, resolution: resolution.value, duration: duration.value,
          userId: userId ?? undefined,
        })
        if (result.taskId) {
          record.taskId = result.taskId
        } else {
          // 鏋佸皯鏁版儏鍐典笅鍚屾杩斿洖缁撴灉
          record.videoUrl = result.videoUrl; record.status = 'done'
          saveRecords(); generating.value = false; return
        }
      }

      saveRecords()
      // 寤惰繜 1.5s 鍚庤В闄?generating 鐘舵€侊紙璁╃敤鎴风湅鍒版彁浜ゆ垚鍔熺殑鍙嶉锛?
      setTimeout(() => generating.value = false, 1500)
      pollVideo(record, userId ?? undefined).catch(console.error)
    } catch (e: any) {
      errorMsg.value = 'API 生成失败：' + e.message
      record.status = 'error'; record.errorMsg = e.message
      saveRecords(); generating.value = false
    }
    return
  }

  // 鏈湴瑙嗛鐢熸垚鏆傛湭瀹炵幇
  errorMsg.value = '本地视频生成暂未实现，请使用 API 调用'
  generating.value = false
}

// 涓嬭浇瑙嗛鍒版湰鍦?
function downloadVideo(url: string, filename?: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename || url.split('/').pop() || 'video.mp4'
  a.click()
}

// 璁板綍姣忎釜瑙嗛鐨勬敹钘忛鑹诧紙key 涓鸿褰?ID锛?=鏈敹钘忥紝1-4=绾㈤粍缁胯摑锛?
const favoritedVideos = ref<Record<string, number>>({})

// 璁剧疆鏌愭潯瑙嗛璁板綍鐨勬敹钘忛鑹?
async function setVideoFavorite(rec: VideoRecord, tag: 0 | 1 | 2 | 3 | 4) {
  if (!rec.outputAssetId) return
  const userStr = localStorage.getItem('user')
  if (!userStr) return
  const user = JSON.parse(userStr)
  try {
    await favoriteAsset(rec.outputAssetId, user.id, tag)
    favoritedVideos.value[rec.id] = tag
  } catch {
    // 闈欓粯澶辫触
  }
}

// 鏁版嵁搴撹褰曡浆鎹㈠嚱鏁帮紝loadMore 鏃跺鐢?
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

// 鈹€鈹€ 瀹氫綅鍘嗗彶璁板綍锛堣祫浜у簱鍙抽敭"瀹氫綅鍘嗗彶璁板綍"璺宠浆杩囨潵锛?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const { pendingRecord, consumePendingLocate } = useLocateHistory()
const locatedRecordId = ref<string | null>(null)

async function locatePendingRecord() {
  const target = consumePendingLocate()
  if (!target) return
  let rec = (records.value as VideoRecord[]).find(r => r.dbId === target.id)
  if (!rec) {
    rec = mapVideoDbRecord(target) as VideoRecord
    records.value.unshift(rec)
  }
  await nextTick()
  const el = document.querySelector(`[data-record-id="${rec.id}"]`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  locatedRecordId.value = rec.id
  setTimeout(() => {
    if (locatedRecordId.value === rec!.id) locatedRecordId.value = null
  }, 1800)
}
// 鍚岄〉闈㈠彸閿?瀹氫綅鍘嗗彶璁板綍"锛堟棤闇€璺宠浆锛夋椂锛宲endingRecord 浼氬湪椤甸潰宸叉寕杞芥椂鍙樺寲
watch(pendingRecord, (r) => { if (r) locatePendingRecord() })

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

// 鈹€鈹€ 娣诲姞鍒伴」鐩?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const showProjectManager = ref(false)
const currentAssetId = ref<number | undefined>(undefined)

function openAddToProjectDialog(assetId: number) {
  currentAssetId.value = assetId
  showProjectManager.value = true
}

function handleProjectManagerClose() {
  showProjectManager.value = false
  currentAssetId.value = undefined
}

// 鈹€鈹€ 鍒濆鍖?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
onMounted(async () => {
  try {
    // 鑾峰彇瑙嗛绫诲瀷鐨?API 妯″瀷鍒楄〃
    apiModels.value = await getApiModels('video')
    if (apiModels.value.length > 0) apiModel.value = apiModels.value[0].id
  } catch {}

  // 浠庢暟鎹簱鍔犺浇鍘嗗彶璁板綍
  const userId = await loadFromDb(mapVideoDbRecord, filterVideoDbRecord)

  // 鎭㈠椤甸潰鍒锋柊鍓嶆湭瀹屾垚鐨勪换鍔¤疆璇?
  const pending = markStaleRecords()
  for (const rec of pending) {
    pollVideo(rec as VideoRecord, userId).catch(console.error)
  }
  saveRecords()

  // 浠庤祫浜у簱鍙抽敭"瀹氫綅鍘嗗彶璁板綍"璺宠浆杩囨潵鐨勶紝姝ゆ椂娑堣垂寰呭畾浣嶈褰?
  await locatePendingRecord()

  // 妫€鏌ユ槸鍚︽湁浠庡浘鐗囬〉闈㈣烦杞繃鏉ョ殑澶嶇敤鍙傛暟
  const reuseData = localStorage.getItem('reuse_record')
  if (reuseData) {
    try {
      const record = JSON.parse(reuseData)
      localStorage.removeItem('reuse_record')
      // 寤惰繜鎵ц锛岀‘淇濇暟鎹姞杞藉畬鎴?
      nextTick(() => {
        handleReuseParams(record, true)  // fromStorage = true
      })
    } catch (e) {
      console.error('解析复用参数失败:', e)
    }
  }

  // 娉ㄥ唽閿洏浜嬩欢鐩戝惉
  window.addEventListener('keydown', handleImageKeydown)
})

// 澶嶇敤鐢熸垚璁板綍鐨勫弬鏁?
function handleReuseParams(record: any, fromStorage = false) {
  // 鍙湁浠庝晶杈规爮鐩存帴璋冪敤鏃舵墠妫€鏌ヨ法椤甸潰璺宠浆
  if (!fromStorage && (record.type === 'txt2img' || record.type === 'img2img')) {
    // 鍥剧墖鐢熸垚璁板綍锛岃烦杞埌鍥剧墖鐢熸垚椤甸潰
    localStorage.setItem('reuse_record', JSON.stringify(record))
    router.push('/image')
    ElMessage.success('已跳转到图片生成页面')
    return
  }

  // 瑙嗛鐢熸垚璁板綍锛屽湪褰撳墠椤甸潰澶勭悊
  // 1. 鍏堟竻绌鸿棰戠敓鎴愮殑鍏抽敭鍙傛暟锛堟彁绀鸿瘝鍜屽弬鑰冪礌鏉愶級
  prompt.value = ''
  clearAllInputs()  // 娓呯┖杈撳叆绱犳潗

  // 2. 鏍规嵁璁板綍绫诲瀷鍒囨崲鏍囩椤?
  if (record.type === 'img2video') {
    activeTab.value = 'img2video'
  } else {
    activeTab.value = 'txt2video'
  }

  // 3. 濉厖鎻愮ず璇?
  prompt.value = record.prompt || ''

  // 4. 灏濊瘯鍖归厤妯″瀷
  if (record.model_name && apiModels.value.length > 0) {
    const matchedModel = apiModels.value.find(m => m.name === record.model_name)
    if (matchedModel) {
      apiModel.value = matchedModel.id
    }
  }

  // 5. 浠?payload 涓仮澶嶅畬鏁村弬鏁?
  if (record.payload) {
    const p = record.payload
    // 瑙嗛姣斾緥
    if (p.ratio) ratio.value = p.ratio
    // 鍒嗚鲸鐜?
    if (p.resolution) resolution.value = p.resolution
    // 鏃堕暱
    if (p.duration) duration.value = p.duration
  }

  // 6. 濡傛灉鏈夎緭鍏ヨ祫浜э紝鍔犺浇鍙傝€冨浘
  if (record.input_asset_ids && record.input_asset_ids.length > 0 && record.input_asset_urls) {
    activeTab.value = 'img2video'
    // 鐩存帴浣跨敤鍚庣杩斿洖鐨?URL
    const assets = record.input_asset_ids.map((id: number, idx: number) => {
      const assetUrl = record.input_asset_urls[idx]
      return {
        id,
        location: assetUrl?.url || `asset_${id}`,
        asset_type: assetUrl?.type === 'video' ? 'video' : 'picture'
      }
    })
    handleAssetSelect(assets)
  }
}

onUnmounted(() => {
  // 绉婚櫎閿洏浜嬩欢鐩戝惉
  window.removeEventListener('keydown', handleImageKeydown)
})
</script>


<template>
  <div class="page">
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <div class="layout">
      <!-- 鈹€鈹€ LEFT PANEL 鈹€鈹€ -->
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
              <ElOption v-for="m in apiModels" :key="m.id" :label="m.description" :value="m.id" />
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

          <!-- 瑙嗛鍙傛暟 -->
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
              <button class="stepper-btn" @click="duration = Math.max(1, duration - 1)">-</button>
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
            <div class="section-label">输入素材（图片最多 4 张，视频最多 1 个，总计最多 2 个）</div>

            <!-- 宸蹭笂浼犳枃浠堕瑙?-->
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

            <!-- 宸查€夋嫨璧勪骇棰勮 -->
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

            <!-- 涓婁紶鎸夐挳 -->
            <div class="upload-actions">
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

            <!-- 闊抽涓婁紶锛堝彲閫夛級 -->
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
              （已上传 {{ allMediaItems.length }} 个素材，可用 @ 引用）
            </span>
          </div>
          <div class="prompt-wrap">
            <ElInput
              ref="promptInputRef"
              v-model="prompt"
              type="textarea" :rows="6"
              :placeholder="activeTab === 'txt2video' ? '输入提示词，描述视频内容、场景、动作...（@ 选择参考素材）' : '描述生成方向...（@ 选择参考素材）'"
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
                <span>@{{ media.type === 'video' ? '视频' : '图片' }}{{ idx + 1 }}</span>
              </div>
            </div>
          </div>

          <!-- generate -->
          <button class="generate-btn" :class="{ loading: generating, submitted: justSubmitted }" :disabled="generating" @click="handleGenerate">
            <span class="btn-glow" />
            <span class="btn-label">{{ justSubmitted ? '已提交' : generating ? '生成中...' : '开始生成' }}</span>
          </button>
        </div>
      </aside>

      <!-- 鈹€鈹€ RIGHT: MESSAGE STREAM 鈹€鈹€ -->
      <main class="right-panel">
        <!-- 缂栬緫妯″紡锛氱紪杈戝櫒 + 鎻愮ず璇嶄晶杈规爮 -->
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

        <!-- 姝ｅ父妯″紡锛氬巻鍙茶褰曪紙濮嬬粓淇濈暀 DOM 闃叉婊氬姩閲嶇疆锛?-->
        <div class="history-col" v-show="!showRecordEditor">
            <div v-if="filteredRecords.length === 0 && records.length === 0" class="empty-wrap">
              <div class="empty-orb" />
              <p class="empty-text">等待生成</p>
            </div>
            <div v-else class="stream">
              <!-- 鎼滅储妗?-->
              <div class="stream-header">
                <span class="stream-title">历史记录 ({{ filteredRecords.length }})</span>
                <input v-model="searchQuery" class="search-input" placeholder="搜索提示词..." />
              </div>

              <div v-for="rec in filteredRecords" :key="rec.id" class="record-row" :data-record-id="rec.id" :class="{ 'record-located': locatedRecordId === rec.id }">
                <!-- 宸︿晶杈撳叆鍥?-->
                <div class="record-input-col">
                  <template v-if="rec.inputAssetUrls && rec.inputAssetUrls.length">
                    <button class="input-toggle-btn" @click="toggleInputExpand(rec.id)">
                      参考素材
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
                <!-- 鍙充晶鍗＄墖 -->
                <RecordCard class="record-card-flex" :record="rec" @delete="deleteRecord" @retry="(r) => retryRecord(r as any)" @edit="handleRecordEdit">
                  <template #prompt>
                    <p class="card-prompt">{{ rec.prompt }}</p>
                  </template>
                  <template #result>
                    <div v-if="rec.videoUrl" class="card-video">
                      <div class="video-thumb" @click="openVideo(rec.videoUrl, rec.outputAssetId)">
                        <video :src="rec.videoUrl" class="video-player" preload="metadata" />
                        <div class="video-play-icon">▶</div>
                        <button class="download-btn" @click.stop="downloadVideo(rec.videoUrl)" title="下载">
                          <span>下载</span>
                        </button>
                        <button v-if="rec.outputAssetId" class="add-to-project-btn" @click.stop="openAddToProjectDialog(rec.outputAssetId)" title="添加到项目">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                          </svg>
                        </button>
                        <span v-if="rec.outputAssetId" class="fav-slot" @click.stop>
                          <FavoriteHeart
                            :tag="favoritedVideos[rec.id] || 0"
                            :size="14"
                            @change="(t) => setVideoFavorite(rec, t)"
                          />
                        </span>
                      </div>
                    </div>
                  </template>
                </RecordCard>
              </div>
              <!-- 鍒嗛〉鎺т欢 -->
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
      <!-- 鈹€鈹€ 鍙充晶璧勪骇渚ц竟鏍?鈹€鈹€ -->
      <AssetSidebar @select="handleAssetSelect" @reuse-params="handleReuseParams" />
    </div>

    <!-- Image Viewer -->
    <Teleport to="body">
      <Transition name="img-viewer">
        <div v-if="showImageViewer" class="custom-image-viewer" @click="showImageViewer = false" @wheel="handleImageWheel">
          <div class="viewer-content" @click.stop>
            <img :src="currentPreviewUrl" class="viewer-image" :style="{ transform: `scale(${imageScale})` }" />
            <button class="viewer-close" @click="showImageViewer = false" title="关闭 (ESC)">×</button>
            <button v-if="previewImageList.length > 1" class="viewer-nav viewer-prev" @click="goToPrevImage" title="上一张">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="15 18 9 12 15 6"/>
              </svg>
            </button>
            <button v-if="previewImageList.length > 1" class="viewer-nav viewer-next" @click="goToNextImage" title="下一张">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </button>
            <div class="viewer-scale-info">{{ Math.round(imageScale * 100) }}%</div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Image Editor锛堣緭鍏ョ礌鏉愮紪杈戯級 -->
    <ImageEditor
      v-if="showEditor"
      :image-src="editingSource === 'file' ? (inputPreviews[editingFileIndex]?.url ?? '') : (selectedAssetPreviews[editingAssetIndex]?.url ?? '')"
      :visible="showEditor"
      @confirm="onEditorConfirmUnified"
      @cancel="onEditorCancel"
    />

    <!-- 鍘嗗彶璁板綍鍥剧墖缂栬緫鍣紙宸插唴鑱斿埌渚ц竟鏍忥級 -->

    <!-- Video Player 寮圭獥 -->
    <VideoPlayer
      :visible="showVideoPlayer"
      :src="activeVideoUrl"
      :asset-id="activeVideoDbId"
      @close="showVideoPlayer = false"
    />

    <!-- 3D 妯″瀷瑙嗚鎴浘 -->
    <ModelViewer v-model:visible="showModelViewer" @capture="handleModelCapture" />

    <!-- 椤圭洰绠＄悊鍣?-->
    <ProjectManager
      :visible="showProjectManager"
      :asset-id="currentAssetId"
      mode="add"
      @close="handleProjectManagerClose"
    />
  </div>
</template>

<style scoped>
@import '../styles/generation-page.css';

/* 鈹€鈹€ 瑙嗛椤典笓灞炴牱寮?鈹€鈹€ */

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

/* 瑙嗛缁撴灉 */
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
.video-thumb:hover .add-to-project-btn {
  opacity: 1;
}
.video-thumb:hover .fav-slot {
  opacity: 1;
}

.fav-slot {
  position: absolute;
  top: 10px; right: 10px;
  opacity: 0;
  transition: opacity 0.2s;
}
.fav-slot:has(.favorited) { opacity: 1; }

.add-to-project-btn {
  position: absolute;
  top: 10px; right: 38px;
  width: 28px; height: 28px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  opacity: 0;
}
.add-to-project-btn:hover {
  background: rgba(108, 99, 255, 0.8);
  border-color: rgba(167, 139, 250, 0.5);
  transform: scale(1.1);
}

.record-row { align-items: center; }
.record-input-col { width: 240px; }

.record-row.record-located {
  border-radius: 16px;
  animation: record-locate-pulse 1.8s ease;
}
@keyframes record-locate-pulse {
  0% { box-shadow: 0 0 0 0 rgba(108,99,255,0.6); background: rgba(108,99,255,0.12); }
  60% { box-shadow: 0 0 0 8px rgba(108,99,255,0); background: rgba(108,99,255,0.12); }
  100% { box-shadow: 0 0 0 0 rgba(108,99,255,0); background: transparent; }
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

/* 鈹€鈹€ 鑷畾涔夊浘鐗囨煡鐪嬪櫒 鈹€鈹€ */
.custom-image-viewer {
  position: fixed;
  inset: 0;
  z-index: 2500;
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.viewer-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  cursor: default;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.viewer-image {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  display: block;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  transition: transform 0.1s ease-out;
  transform-origin: center center;
}
.viewer-close {
  position: absolute;
  top: -40px;
  right: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(0, 0, 0, 0.4);
  color: rgba(255, 255, 255, 0.9);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.viewer-close:hover {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.4);
  transform: scale(1.1);
}
.viewer-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(0, 0, 0, 0.5);
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.viewer-nav:hover {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.4);
  transform: translateY(-50%) scale(1.1);
}
.viewer-prev {
  left: -60px;
}
.viewer-next {
  right: -60px;
}
.viewer-scale-info {
  position: absolute;
  bottom: -35px;
  left: 50%;
  transform: translateX(-50%);
  padding: 4px 12px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.8);
  font-size: 12px;
  pointer-events: none;
}

.img-viewer-enter-active,
.img-viewer-leave-active {
  transition: opacity 0.25s ease;
}
.img-viewer-enter-active .viewer-content,
.img-viewer-leave-active .viewer-content {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.img-viewer-enter-from,
.img-viewer-leave-to {
  opacity: 0;
}
.img-viewer-enter-from .viewer-content,
.img-viewer-leave-to .viewer-content {
  transform: scale(0.9);
  opacity: 0;
}

/* 缁熶竴涓哄弬鏁伴潰鏉块鏍?*/
.prompt-hint {
  color: var(--color-muted);
}

.filter-btn {
  border-color: var(--color-border);
  background: rgba(255,255,255,0.03);
  color: var(--color-faint);
}
.filter-btn:hover {
  border-color: rgba(255,255,255,0.22);
  background: rgba(255,255,255,0.06);
  color: var(--color-muted);
}
.filter-btn.active {
  border-color: rgba(255,255,255,0.24);
  background: rgba(255,255,255,0.1);
  color: var(--color-text);
}

.stepper:hover,
.asset-btn:hover,
.local-upload-btn:hover,
.audio-upload-btn:hover {
  border-color: rgba(255,255,255,0.24);
  background: rgba(255,255,255,0.06);
  color: var(--color-text);
}
.stepper-btn:hover,
.edit-btn:hover,
.add-to-project-btn:hover {
  background: rgba(255,255,255,0.18);
  border-color: rgba(255,255,255,0.34);
}

.record-row.record-located {
  animation: record-locate-soft 1.8s ease;
}
@keyframes record-locate-soft {
  0% { box-shadow: 0 0 0 0 rgba(255,255,255,0.32); background: rgba(255,255,255,0.08); }
  60% { box-shadow: 0 0 0 8px rgba(255,255,255,0); background: rgba(255,255,255,0.08); }
  100% { box-shadow: 0 0 0 0 rgba(255,255,255,0); background: transparent; }
}

.page-size-btn:hover,
.page-size-btn.active,
.load-more-btn {
  border-color: var(--color-border);
}
.page-size-btn.active {
  background: rgba(255,255,255,0.1);
  color: var(--color-text);
}
.load-more-btn {
  background: rgba(255,255,255,0.055);
  color: var(--color-muted);
}
.load-more-btn:hover:not(:disabled) {
  background: rgba(255,255,255,0.1);
  color: var(--color-text);
}
</style>

