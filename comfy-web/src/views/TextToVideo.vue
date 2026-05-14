<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { ElInput, ElSelect, ElOption } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import AssetPicker from '../components/AssetPicker.vue'
import RecordCard from '../components/RecordCard.vue'
import { apiVideoGenerate, apiImg2VideoGenerate, getApiModels, type ApiModel } from '../api/apiService'
import { useTaskHistory } from '../composables/useTaskHistory'
import { getCurrentUserId } from '../utils/user'

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
  mode: 'txt2video' | 'img2video'  // 记录是文生视频还是图生视频
  inputFiles?: File[]  // 保存输入的文件
  inputAssetIds?: number[]  // 保存输入的资产ID
}

const HISTORY_KEY = 'video_generation_history'
const MAX_RECORDS = 50

const { records, saveRecords, clearAll, deleteRecord } = useTaskHistory<VideoRecord>(
  HISTORY_KEY,
  MAX_RECORDS,
  () => ({ inputFiles: undefined }),
)

async function retryRecord(record: VideoRecord) {
  // 创建新记录，复用原来的参数
  const newRecord: VideoRecord = {
    id: crypto.randomUUID(),
    createdAt: Date.now(),
    prompt: record.prompt,
    modelName: record.modelName,
    ratio: record.ratio,
    resolution: record.resolution,
    duration: record.duration,
    status: 'generating',
    mode: record.mode,
    inputFiles: record.inputFiles,
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
        input_files: record.inputFiles || [],
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

const isImg2Video = computed(() => activeTab.value === 'img2video')

const maxImages = 9
const maxVideos = 3
const maxTotal = 12

// 素材列表变化时，自动在 prompt 开头插入/更新素材标签
watch([inputPreviews, selectedAssetPreviews], ([files, assets]) => {
  if (activeTab.value !== 'img2video' || modelSource.value !== 'api') return

  const allMedia = [...files, ...assets]
  if (allMedia.length === 0) {
    // 移除旧的素材标签前缀
    prompt.value = prompt.value.replace(/^(\[(图|视频)\d+\]\s*)+/, '')
    return
  }

  // 移除旧的素材标签前缀
  const cleaned = prompt.value.replace(/^(\[(图|视频)\d+\]\s*)+/, '')

  // 构建新的标签
  const labels = allMedia.map((media, i) => {
    const type = media.type === 'video' ? '视频' : '图'
    return `[${type}${i + 1}]`
  }).join(' ')

  prompt.value = labels + (cleaned ? ' ' + cleaned : '')
}, { deep: true })

onMounted(async () => {
  // 加载 API 模型
  try {
    apiModels.value = await getApiModels('video')
    if (apiModels.value.length > 0) apiModel.value = apiModels.value[0].id
  } catch {}

  // 恢复刷新前未完成的 API 任务
  const userId = getCurrentUserId()
  const pending = records.value.filter(r => r.status === 'generating' && r.taskId)
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
      url: `/api/view?filename=${encodeURIComponent(asset.location)}&type=output`,
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
        // 已完成，直接用结果
        console.log('[Video] Task completed, result:', checkData.result)
        const rec = records.value.find(r => r.id === record.id)
        if (rec) {
          const videoItem = checkData.result.find((item: any) => item.type === 'video')
          console.log('[Video] Found video item:', videoItem)
          rec.videoUrl = videoItem?.url || ''
          rec.status = 'done'
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

    const modelName = apiModels.value.find(m => m.id === apiModel.value)?.name || apiModel.value

    const record: VideoRecord = {
      id: crypto.randomUUID(),
      createdAt: Date.now(),
      prompt: prompt.value,
      modelName,
      ratio: ratio.value,
      resolution: resolution.value,
      duration: duration.value,
      status: 'generating',
      mode: activeTab.value,  // 记录是文生视频还是图生视频
      inputFiles: activeTab.value === 'img2video' ? [...inputFiles.value] : undefined,
      inputAssetIds: activeTab.value === 'img2video' ? [...selectedAssetIds.value] : undefined,
    }
    records.value.unshift(record)
    saveRecords()

    // 获取 user_id
    const userId = getCurrentUserId()

    try {
      let taskId: string

      // 图生视频模式
      if (activeTab.value === 'img2video') {
        // 检查是否有输入
        if (inputFiles.value.length === 0 && selectedAssetIds.value.length === 0) {
          errorMsg.value = '请上传图片/视频或从资产选择'
          generating.value = false
          records.value.shift()
          saveRecords()
          return
        }

        console.log('[handleGenerate] inputFiles:', inputFiles.value.length, 'selectedAssetIds:', selectedAssetIds.value.length)
        console.log('[handleGenerate] inputFiles details:', inputFiles.value.map(f => ({ name: f.name, size: f.size, type: f.type })))

        const result = await apiImg2VideoGenerate({
          model: apiModel.value,
          prompt: prompt.value,
          user_id: userId,
          ratio: ratio.value,
          resolution: resolution.value,
          duration: duration.value,
          input_files: inputFiles.value,
          input_asset_ids: selectedAssetIds.value,
        })

        taskId = result.task_id
      }
      // 文生视频模式
      else {
        const result = await apiVideoGenerate({
          model: apiModel.value,
          prompt: prompt.value,
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
                <button class="remove-btn" @click="removeFile(index)">×</button>
                <span class="preview-badge">{{ preview.type === 'video' ? '视频' : '图片' }}{{ index + 1 }}</span>
              </div>
            </div>

            <!-- 已选择资产预览 -->
            <div v-if="selectedAssetPreviews.length > 0" class="previews-grid">
              <div v-for="(preview, index) in selectedAssetPreviews" :key="'asset-' + preview.id" class="preview-item">
                <video v-if="preview.type === 'video'" :src="preview.url" class="preview-media" />
                <img v-else :src="preview.url" class="preview-media" />
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
            <span v-if="activeTab === 'img2video' && (inputPreviews.length > 0 || selectedAssetPreviews.length > 0)" class="prompt-hint">
              （已上传{{ inputPreviews.length + selectedAssetPreviews.length }}个素材，可在提示词中使用编号引用）
            </span>
          </div>
          <ElInput
            v-model="prompt"
            type="textarea" :rows="6"
            :placeholder="activeTab === 'txt2video' ? '输入提示词，描述视频内容、场景、动作...' : ''"
            class="prompt-input"
          />

          <!-- generate -->
          <button class="generate-btn" :class="{ loading: generating }" :disabled="generating" @click="handleGenerate">
            <span class="btn-glow" />
            <span class="btn-label">{{ generating ? '生成中...' : '开始生成' }}</span>
          </button>
        </div>
      </aside>

      <!-- ── RIGHT: MESSAGE STREAM ── -->
      <main class="right-panel">
        <div v-if="records.length === 0" class="empty-wrap">
          <div class="empty-orb" />
          <p class="empty-text">等待生成</p>
        </div>
        <div v-else class="stream">
          <!-- 清空按钮 -->
          <div class="stream-header">
            <span class="stream-title">历史记录 ({{ records.length }})</span>
            <button class="clear-all-btn" @click="clearAll">清空全部</button>
          </div>

          <div v-for="rec in records" :key="rec.id">
            <RecordCard :record="rec" @delete="deleteRecord" @retry="(r) => retryRecord(r as any)">
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
.prompt-input { width: 100%; }

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
  aspect-ratio: 1;
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
  align-items: center;
  justify-content: flex-start;
  padding: 32px 40px;
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

.clear-all-btn {
  padding: 6px 16px;
  background: rgba(248,113,113,0.1);
  border: 1px solid rgba(248,113,113,0.2);
  border-radius: 6px;
  color: #f87171;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.clear-all-btn:hover {
  background: rgba(248,113,113,0.2);
  border-color: rgba(248,113,113,0.4);
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
