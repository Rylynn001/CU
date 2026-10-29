<template>
  <div class="chat-page">
    <!-- 左侧会话列表 -->
    <div class="sessions-sidebar">
      <div class="sidebar-header">
        <h2>会话列表</h2>
        <button class="new-session-btn" @click="createNewSession" :disabled="isProcessing">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M12 5v14M5 12h14" stroke-width="2" stroke-linecap="round"/>
          </svg>
          新会话
        </button>
      </div>

      <div class="sessions-list">
        <div
          v-for="session in sessions"
          :key="session.id"
          :class="['session-item', { active: session.id === currentSessionId }]"
          @click="switchSession(session.id)"
        >
          <div class="session-info">
            <div class="session-title">{{ session.intent || '新会话' }}</div>
            <div class="session-meta">
              <span class="session-status" :class="session.status">{{ getStatusText(session.status) }}</span>
              <span class="session-time">{{ formatTime(session.updated_at) }}</span>
            </div>
          </div>
        </div>

        <div v-if="sessions.length === 0" class="empty-sessions">
          暂无会话
        </div>
      </div>
    </div>

    <!-- 右侧对话区域 -->
    <div class="chat-content">
      <div v-if="isLoadingModels" class="loading-container">
        <p>正在加载模型...</p>
      </div>

      <template v-else>
      <div v-if="!currentSessionId && messages.length === 0" class="welcome-container">
        <AiMascotInput
          title="我能为您做什么？"
          subtitle="输入提示词或语音输入开始对话"
          :show-welcome="true"
          :on-submit="handleSubmit"
          :is-processing="isProcessing"
          :models="availableModels"
          :default-model-id="availableModels[0]?.id"
          :enable-voice="true"
          :enable-web-search="true"
          :enable-attachments="true"
        />
      </div>

      <div v-else class="chat-container">
        <div class="messages-container" ref="messagesContainer">
          <div v-for="(msg, idx) in messages" :key="idx" :class="['message', msg.role]">
            <div class="message-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
            <div class="message-bubble">
              <div v-if="isProcessing && idx === messages.length - 1 && currentStatus" class="message-status">
                <span class="status-dot"></span>{{ currentStatus }}
              </div>
              <div class="message-content">{{ msg.message }}</div>
              <div class="message-time">{{ formatTime(msg.created_at) }}</div>
            </div>
          </div>
          <section v-for="task in activeTasks" :key="task.execution_id" class="task-result">
            <div class="task-heading">
              <strong>{{ task.model_name || (task.media_type === 'video' ? '视频生成' : '图片生成') }}</strong>
              <span class="task-status" :class="task.status">{{ getTaskStatusText(task) }}</span>
            </div>
            <div class="task-prompt">{{ task.parameters?.prompt }}</div>
            <div v-if="task.status === 'running'" class="task-meta">
              任务编号：{{ task.task_id }}<span v-if="task.stage"> · {{ task.stage }}</span>
            </div>
            <div v-if="task.status === 'failed'" class="task-error">{{ task.error || '生成失败' }}</div>
            <div v-if="task.images?.length" class="task-images">
              <a v-for="image in task.images" :key="image.asset_id" :href="image.url" target="_blank" rel="noreferrer">
                <img :src="image.url" :alt="task.parameters?.prompt || '生成图片'" loading="lazy" />
              </a>
            </div>
            <div v-if="task.videos?.length" class="task-images">
              <video v-for="video in task.videos" :key="video.asset_id" :src="video.url" controls />
            </div>
          </section>
        </div>

        <div class="input-container">
          <AiMascotInput
            :show-welcome="false"
            :on-submit="handleSubmit"
            :is-processing="isProcessing"
            :models="availableModels"
            :default-model-id="availableModels[0]?.id"
            :enable-voice="true"
            :enable-web-search="false"
            :enable-attachments="true"
          />
        </div>
      </div>

      <el-dialog v-model="generationDialogOpen" :title="generationType === 'video' ? '确认视频生成参数' : '确认图片生成参数'" width="min(520px, 92vw)" :close-on-click-modal="false">
        <p class="generation-dialog-prompt">{{ pendingGenerationPrompt }}</p>
        <div class="generation-dialog-fields">
          <el-select v-model="generationModelId" placeholder="选择生成模型" clearable>
            <el-option v-for="model in generationModels" :key="model.id" :label="`${model.name} · ${model.provider}`" :value="model.id" />
          </el-select>
          <template v-if="generationType === 'image'">
            <el-select v-model="imageAspectRatio" placeholder="选择比例" clearable>
              <el-option label="1:1" value="1:1" /><el-option label="16:9" value="16:9" /><el-option label="9:16" value="9:16" /><el-option label="4:3" value="4:3" /><el-option label="3:4" value="3:4" />
            </el-select>
            <el-select v-model="imageQuality" placeholder="选择质量" clearable>
              <el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" />
            </el-select>
            <el-input-number v-model="imageCount" :min="1" :max="10" placeholder="张数" />
          </template>
          <template v-else>
            <el-select v-model="videoRatio" placeholder="选择比例" clearable>
              <el-option label="16:9" value="16:9" /><el-option label="9:16" value="9:16" /><el-option label="1:1" value="1:1" />
            </el-select>
            <el-select v-model="videoResolution" placeholder="选择分辨率" clearable>
              <el-option label="720p" value="720p" /><el-option label="1080p" value="1080p" />
            </el-select>
            <el-input-number v-model="videoDuration" :min="1" :max="60" placeholder="秒数" />
          </template>
        </div>
        <p v-if="generationDialogError" class="task-error">{{ generationDialogError }}</p>
        <template #footer>
          <el-button @click="generationDialogOpen = false">取消</el-button>
          <el-button type="primary" @click="confirmGeneration">确认并生成</el-button>
        </template>
      </el-dialog>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import AiMascotInput from '@/components/AiMascotInput.vue'
import type { ChatSubmitData, AIModel } from '@/types/ai-models'
import {
  sendWorkflowMessageStream,
  getLanguageModels,
  getUserSessions,
  getSessionHistory,
  getTaskStatus,
  type WorkflowMessageRequest,
  type WorkflowMessageResponse,
  type WorkflowSession,
  type WorkflowTask,
  type ConversationMessage,
} from '@/api/workflow'

const isProcessing = ref(false)
const currentStatus = ref('')
const messages = ref<Array<ConversationMessage & { role: 'user' | 'agent' }>>([])
const availableModels = ref<AIModel[]>([])
const isLoadingModels = ref(true)
const currentSessionId = ref<string | undefined>(undefined)
const sessions = ref<WorkflowSession[]>([])
const messagesContainer = ref<HTMLElement | null>(null)
const activeTasks = ref<WorkflowTask[]>([])
const generationType = ref<'none' | 'image' | 'video'>('none')
const generationModels = ref<Array<{ id: number; name: string; provider: string; description?: string }>>([])
const generationModelId = ref<number | null>(null)
const imageCount = ref<number | null>(null)
const imageAspectRatio = ref<string | null>(null)
const imageQuality = ref<string | null>(null)
const videoRatio = ref<string | null>(null)
const videoResolution = ref<string | null>(null)
const videoDuration = ref<number | null>(null)
const generationDialogOpen = ref(false)
const generationDialogError = ref('')
const pendingGenerationPrompt = ref('')
let lastSubmitData: ChatSubmitData | undefined
let pollingTasks = false
let taskPoller: ReturnType<typeof setInterval> | undefined

// 状态文本映射
function getStatusText(status: string): string {
  const statusMap: Record<string, string> = {
    collecting: '收集中',
    ready: '准备就绪',
    generating: '生成中',
    executing: '执行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
  }
  return statusMap[status] || status
}

function getTaskStatusText(task: WorkflowTask): string {
  if (task.status === 'running') return '生成中'
  if (task.status === 'completed') return '已完成'
  if (task.status === 'failed') return '失败'
  return task.status
}

// 时间格式化
function formatTime(dateStr: string): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  return date.toLocaleDateString('zh-CN')
}

// 滚动到底部
function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 从后端数据构建前端 AIModel 格式
function buildAIModel(backendModel: any): AIModel {
  const providerMap: Record<string, { iconName: AIModel['iconName']; badgeColor: string; accentColor: string }> = {
    openai: {
      iconName: 'openai',
      badgeColor: 'text-emerald-500',
      accentColor: '#10a37f',
    },
    anthropic: {
      iconName: 'anthropic',
      badgeColor: 'text-amber-500',
      accentColor: '#d97706',
    },
    gemini: {
      iconName: 'gemini',
      badgeColor: 'text-blue-500',
      accentColor: '#3b82f6',
    },
    mistral: {
      iconName: 'mistral',
      badgeColor: 'text-orange-500',
      accentColor: '#f97316',
    },
  }

  const providerKey = backendModel.provider.toLowerCase()
  const providerConfig = providerMap[providerKey] || providerMap.openai

  return {
    id: String(backendModel.id),
    name: backendModel.name,
    provider: backendModel.provider,
    iconName: providerConfig.iconName,
    badgeColor: providerConfig.badgeColor,
    accentColor: providerConfig.accentColor,
    reasoningTitle: '推理强度',
    defaultLevel: 'medium',
    levels: [
      { id: 'low', label: '低', desc: '快速响应', multiplier: 1.8 },
      { id: 'medium', label: '中', desc: '平衡推理', multiplier: 2.6 },
      { id: 'high', label: '高', desc: '深度推理', multiplier: 3.6 },
    ],
  }
}

// 加载语言模型列表
async function loadLanguageModels() {
  try {
    isLoadingModels.value = true
    const models = await getLanguageModels()
    availableModels.value = models.map(buildAIModel)
    console.log('已加载语言模型:', availableModels.value)
  } catch (error) {
    console.error('加载语言模型失败:', error)
    availableModels.value = [
      {
        id: 'fallback',
        name: 'GPT-4',
        provider: 'OpenAI',
        iconName: 'openai',
        badgeColor: 'text-emerald-500',
        accentColor: '#10a37f',
        reasoningTitle: '推理强度',
        defaultLevel: 'medium',
        levels: [
          { id: 'low', label: '低', desc: '快速响应', multiplier: 1.8 },
          { id: 'medium', label: '中', desc: '平衡推理', multiplier: 2.6 },
          { id: 'high', label: '高', desc: '深度推理', multiplier: 3.6 },
        ],
      },
    ]
  } finally {
    isLoadingModels.value = false
  }
}

// 加载会话列表
async function loadSessions() {
  try {
    sessions.value = await getUserSessions()
    console.log('已加载会话列表:', sessions.value)
  } catch (error) {
    console.error('加载会话列表失败:', error)
  }
}

// 加载会话详情
async function loadSessionDetail(sessionId: string) {
  try {
    const detail = await getSessionHistory(sessionId)
    messages.value = detail.conversations as any
    activeTasks.value = detail.tasks || []
    if (detail.parameters?.generation_request) openGenerationDialog(detail.parameters.generation_request)
    scrollToBottom()
  } catch (error) {
    console.error('加载会话详情失败:', error)
    messages.value = []
    activeTasks.value = []
  }
}

// 切换会话
async function switchSession(sessionId: string) {
  if (sessionId === currentSessionId.value || isProcessing.value) return
  currentSessionId.value = sessionId
  generationDialogOpen.value = false
  await loadSessionDetail(sessionId)
}

// 创建新会话
function createNewSession() {
  if (isProcessing.value) return
  currentSessionId.value = undefined
  messages.value = []
  activeTasks.value = []
  generationDialogOpen.value = false
}

function openGenerationDialog(request: NonNullable<WorkflowMessageResponse['generation_request']>) {
  generationType.value = request.media_type
  generationModels.value = request.models
  pendingGenerationPrompt.value = request.prompt
  generationModelId.value = null
  imageCount.value = null
  imageAspectRatio.value = null
  imageQuality.value = null
  videoRatio.value = null
  videoResolution.value = null
  videoDuration.value = null
  generationDialogError.value = ''
  generationDialogOpen.value = true
}

async function confirmGeneration() {
  if (isProcessing.value) return
  const options: WorkflowMessageRequest['generation_options'] = generationType.value === 'image'
    ? { media_type: 'image', model: generationModelId.value, n: imageCount.value, aspect_ratio: imageAspectRatio.value, quality: imageQuality.value }
    : { media_type: 'video', model: generationModelId.value, ratio: videoRatio.value, resolution: videoResolution.value, duration: videoDuration.value }
  if (Object.values(options).some((value) => value === null || value === undefined || value === '')) {
    generationDialogError.value = '请先选择模型，并填写全部生成参数。'
    return
  }
  const selected = generationModels.value.find((model) => model.id === generationModelId.value)
  if (selected?.provider === 'gemini' && generationType.value === 'image' && imageCount.value !== 1) {
    generationDialogError.value = '当前模型每次支持生成一张图片，请选择一张。'
    return
  }
  const model = lastSubmitData?.model || availableModels.value[0]
  if (!model) { generationDialogError.value = '请先加载对话模型后重试。'; return }
  generationDialogOpen.value = false
  await handleSubmit({ prompt: pendingGenerationPrompt.value, model, effort: model.defaultLevel, useWebSearch: false, attachedFile: null }, options)
}

// 处理消息提交
const handleSubmit = async (data: ChatSubmitData, confirmedOptions?: WorkflowMessageRequest['generation_options']) => {
  if (isProcessing.value) return
  lastSubmitData = data
  console.log('用户提交:', data)

  // 乐观更新：立即添加用户消息到界面
  const userMessage: ConversationMessage = {
    role: 'user',
    message: data.prompt,
    created_at: new Date().toISOString(),
  }
  messages.value.push(userMessage as any)
  messages.value.push({
    role: 'agent',
    message: '',
    created_at: new Date().toISOString(),
  })
  scrollToBottom()

  isProcessing.value = true

  try {
    // 调用后端 API
    const response = await sendWorkflowMessageStream(
      { message: data.prompt, model_id: Number(data.model.id), session_id: currentSessionId.value, generation_options: confirmedOptions },
      (status) => {
        currentStatus.value = status
        console.info('[工作流对话]', status)
      },
      (text) => {
        const lastMessage = messages.value[messages.value.length - 1]
        if (lastMessage?.role === 'agent') lastMessage.message += text
        scrollToBottom()
      },
    )
    activeTasks.value = response.tasks || []
    if (response.generation_request) {
      openGenerationDialog(response.generation_request)
    }

    // 更新 session_id
    const sessionChanged = Boolean(response.session_id && response.session_id !== currentSessionId.value)
    if (sessionChanged) {
      currentSessionId.value = response.session_id
      // 刷新会话列表
      await loadSessions()
    }

    // 添加 AI 回复
    const agentMessage = messages.value[messages.value.length - 1]
    if (agentMessage?.role === 'agent' && !agentMessage.message) {
      agentMessage.message = response.reply
    }
    scrollToBottom()

    // 如果工作流准备就绪，刷新会话列表（状态可能已变化）
    if (response.workflow_ready && !sessionChanged) {
      await loadSessions()
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    const errorMessage = messages.value[messages.value.length - 1]
    if (errorMessage?.role === 'agent') {
      errorMessage.message = error instanceof Error ? error.message : '抱歉，处理您的请求时出现错误。'
    }
    scrollToBottom()
  } finally {
    isProcessing.value = false
    currentStatus.value = ''
  }
}

onMounted(async () => {
  await loadLanguageModels()
  await loadSessions()

  // 如果有会话，自动加载最新的一个（可选）
  if (sessions.value.length > 0) {
    const latestSession = sessions.value[0]
    currentSessionId.value = latestSession.id
    await loadSessionDetail(latestSession.id)
  }

  taskPoller = setInterval(async () => {
    if (pollingTasks || !currentSessionId.value || !activeTasks.value.some((task) => task.status === 'running')) return
    pollingTasks = true
    const sessionId = currentSessionId.value
    try {
    for (const task of activeTasks.value.filter((item) => item.status === 'running')) {
      try {
        const status = await getTaskStatus(task.task_id)
        if (sessionId !== currentSessionId.value) return
        if (status.status === 'completed' || status.status === 'failed') {
          const detail = await getSessionHistory(sessionId)
          if (sessionId !== currentSessionId.value) return
          activeTasks.value = detail.tasks || []
          await loadSessions()
          break
        }
        task.stage = status.status
      } catch (error) {
        console.error('刷新生成任务状态失败:', error)
      }
    }
    } finally {
      pollingTasks = false
    }
  }, 3000)
})

onUnmounted(() => {
  if (taskPoller) clearInterval(taskPoller)
})
</script>

<style scoped>
.chat-page {
  display: flex;
  width: 100%;
  height: 100vh;
  background: var(--color-black);
  color: var(--color-white);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

/* ===== 左侧会话列表 ===== */
.sessions-sidebar {
  width: 280px;
  background: var(--color-bg);
  border-right: 1px solid rgba(var(--color-white-rgb), 0.1);
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 1.5rem 1rem;
  border-bottom: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.sidebar-header h2 {
  font-size: 1.125rem;
  font-weight: 600;
  margin: 0 0 1rem 0;
  color: var(--color-text);
}

.new-session-btn {
  width: 100%;
  padding: 0.625rem 1rem;
  background: rgba(var(--color-info-rgb), 0.1);
  border: 1px solid rgba(var(--color-info-rgb), 0.3);
  border-radius: 0.5rem;
  color: var(--color-info);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  transition: all 0.2s;
}

.new-session-btn:hover:not(:disabled) {
  background: rgba(var(--color-info-rgb), 0.2);
  border-color: rgba(var(--color-info-rgb), 0.5);
}

.new-session-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sessions-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
}

.session-item {
  padding: 0.875rem;
  margin-bottom: 0.5rem;
  background: rgba(var(--color-white-rgb), 0.02);
  border: 1px solid rgba(var(--color-white-rgb), 0.05);
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.session-item:hover {
  background: rgba(var(--color-white-rgb), 0.05);
  border-color: rgba(var(--color-white-rgb), 0.1);
}

.session-item.active {
  background: rgba(var(--color-info-rgb), 0.1);
  border-color: rgba(var(--color-info-rgb), 0.3);
}

.session-title {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text);
  margin-bottom: 0.5rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.75rem;
  color: rgba(var(--color-text-soft-rgb), 0.5);
}

.session-status {
  padding: 0.125rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.6875rem;
}

.session-status.collecting {
  background: rgba(var(--color-danger-rgb), 0.1);
  color: var(--color-danger);
}

.session-status.ready {
  background: rgba(var(--color-success-rgb), 0.1);
  color: rgb(var(--color-success-rgb));
}

.session-status.completed {
  background: rgba(var(--color-info-rgb), 0.1);
  color: var(--color-info);
}

.session-status.failed {
  background: rgba(var(--color-danger-rgb), 0.1);
  color: var(--color-danger);
}

.empty-sessions {
  padding: 2rem 1rem;
  text-align: center;
  color: rgba(var(--color-text-soft-rgb), 0.3);
  font-size: 0.875rem;
}

/* ===== 右侧对话区域 ===== */
.chat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.generation-dialog-prompt { margin: 0 0 1rem; white-space: pre-wrap; }
.generation-dialog-fields { display: grid; gap: 1rem; }
.generation-dialog-fields :deep(.el-select), .generation-dialog-fields :deep(.el-input-number) { width: 100%; }

.loading-container {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(var(--color-white-rgb), 0.6);
}

.welcome-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.message {
  display: flex;
  gap: 1rem;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-avatar {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.5rem;
  background: rgba(var(--color-white-rgb), 0.05);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  flex-shrink: 0;
}

.message.user .message-avatar {
  background: rgba(var(--color-info-rgb), 0.1);
}

.message.agent .message-avatar {
  background: rgba(var(--color-danger-rgb), 0.1);
}

.message-bubble {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.message-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 0.5rem;
  color: var(--color-text-soft);
  font-size: 0.875rem;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-info);
  animation: statusPulse 1s ease-in-out infinite alternate;
}

@keyframes statusPulse {
  to { opacity: 0.35; }
}

.message-content {
  padding: 1rem;
  background: rgba(var(--color-white-rgb), 0.05);
  border-radius: 0.75rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.message.user .message-content {
  background: rgba(var(--color-info-rgb), 0.1);
}

.message-time {
  font-size: 0.75rem;
  color: rgba(var(--color-text-soft-rgb), 0.4);
  padding: 0 0.5rem;
}

.task-result {
  margin-left: 3.5rem;
  padding: 1rem;
  border: 1px solid rgba(var(--color-white-rgb), 0.12);
  border-radius: 0.5rem;
  background: rgba(var(--color-white-rgb), 0.04);
}

.task-heading { display: flex; justify-content: space-between; gap: 1rem; }
.task-status { color: var(--color-info); }
.task-status.completed { color: rgb(var(--color-success-rgb)); }
.task-status.failed, .task-error { color: var(--color-danger); }
.task-prompt, .task-meta { margin-top: 0.5rem; color: rgba(var(--color-white-rgb), 0.65); }
.task-images { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 0.75rem; }
.task-images img { display: block; width: min(100%, 320px); max-height: 320px; object-fit: contain; border-radius: 4px; }
.task-images video { display: block; width: min(100%, 480px); max-height: 320px; border-radius: 4px; }

.input-container {
  padding: 1.5rem;
  border-top: 1px solid rgba(var(--color-white-rgb), 0.1);
  background: var(--color-bg);
}

/* 滚动条样式 */
.sessions-list::-webkit-scrollbar,
.messages-container::-webkit-scrollbar {
  width: 6px;
}

.sessions-list::-webkit-scrollbar-track,
.messages-container::-webkit-scrollbar-track {
  background: transparent;
}

.sessions-list::-webkit-scrollbar-thumb,
.messages-container::-webkit-scrollbar-thumb {
  background: rgba(var(--color-white-rgb), 0.1);
  border-radius: 3px;
}

.sessions-list::-webkit-scrollbar-thumb:hover,
.messages-container::-webkit-scrollbar-thumb:hover {
  background: rgba(var(--color-white-rgb), 0.2);
}
</style>
