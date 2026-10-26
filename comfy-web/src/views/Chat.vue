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

      <div v-else-if="!currentSessionId && messages.length === 0" class="welcome-container">
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
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            :class="['message', msg.role]"
          >
            <div class="message-avatar">
              {{ msg.role === 'user' ? '👤' : '🤖' }}
            </div>
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
                <img :src="image.url" :alt="task.parameters?.prompt || '生成图片'" />
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
  await loadSessionDetail(sessionId)
}

// 创建新会话
function createNewSession() {
  if (isProcessing.value) return
  currentSessionId.value = undefined
  messages.value = []
  activeTasks.value = []
}

// 处理消息提交
const handleSubmit = async (data: ChatSubmitData) => {
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
      { message: data.prompt, session_id: currentSessionId.value },
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

    // 更新 session_id
    if (response.session_id && response.session_id !== currentSessionId.value) {
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
    if (response.workflow_ready) {
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
    if (!currentSessionId.value || !activeTasks.value.some((task) => task.status === 'running')) return
    try {
      const detail = await getSessionHistory(currentSessionId.value)
      activeTasks.value = detail.tasks || []
      await loadSessions()
    } catch (error) {
      console.error('刷新图片任务状态失败:', error)
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
  background: #000;
  color: #fff;
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

/* ===== 左侧会话列表 ===== */
.sessions-sidebar {
  width: 280px;
  background: #0F172A;
  border-right: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 1.5rem 1rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.sidebar-header h2 {
  font-size: 1.125rem;
  font-weight: 600;
  margin: 0 0 1rem 0;
  color: #F8FAFC;
}

.new-session-btn {
  width: 100%;
  padding: 0.625rem 1rem;
  background: rgba(56, 189, 248, 0.1);
  border: 1px solid rgba(56, 189, 248, 0.3);
  border-radius: 0.5rem;
  color: #38BDF8;
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
  background: rgba(56, 189, 248, 0.2);
  border-color: rgba(56, 189, 248, 0.5);
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
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.1);
}

.session-item.active {
  background: rgba(56, 189, 248, 0.1);
  border-color: rgba(56, 189, 248, 0.3);
}

.session-title {
  font-size: 0.875rem;
  font-weight: 500;
  color: #F8FAFC;
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
  color: rgba(248, 250, 252, 0.5);
}

.session-status {
  padding: 0.125rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.6875rem;
}

.session-status.collecting {
  background: rgba(249, 115, 22, 0.1);
  color: #F97316;
}

.session-status.ready {
  background: rgba(34, 197, 94, 0.1);
  color: #22C55E;
}

.session-status.completed {
  background: rgba(56, 189, 248, 0.1);
  color: #38BDF8;
}

.session-status.failed {
  background: rgba(239, 68, 68, 0.1);
  color: #EF4444;
}

.empty-sessions {
  padding: 2rem 1rem;
  text-align: center;
  color: rgba(248, 250, 252, 0.3);
  font-size: 0.875rem;
}

/* ===== 右侧对话区域 ===== */
.chat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.loading-container {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.6);
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
  background: rgba(255, 255, 255, 0.05);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  flex-shrink: 0;
}

.message.user .message-avatar {
  background: rgba(56, 189, 248, 0.1);
}

.message.agent .message-avatar {
  background: rgba(249, 115, 22, 0.1);
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
  color: #a1a1aa;
  font-size: 0.875rem;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #38bdf8;
  animation: statusPulse 1s ease-in-out infinite alternate;
}

@keyframes statusPulse {
  to { opacity: 0.35; }
}

.message-content {
  padding: 1rem;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 0.75rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.message.user .message-content {
  background: rgba(56, 189, 248, 0.1);
}

.message-time {
  font-size: 0.75rem;
  color: rgba(248, 250, 252, 0.4);
  padding: 0 0.5rem;
}

.task-result {
  margin-left: 3.5rem;
  padding: 1rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 0.5rem;
  background: rgba(255, 255, 255, 0.04);
}

.task-heading { display: flex; justify-content: space-between; gap: 1rem; }
.task-status { color: #38bdf8; }
.task-status.completed { color: #22c55e; }
.task-status.failed, .task-error { color: #f87171; }
.task-prompt, .task-meta { margin-top: 0.5rem; color: rgba(255, 255, 255, 0.65); }
.task-images { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 0.75rem; }
.task-images img { display: block; width: min(100%, 320px); max-height: 320px; object-fit: contain; border-radius: 4px; }
.task-images video { display: block; width: min(100%, 480px); max-height: 320px; border-radius: 4px; }

.input-container {
  padding: 1.5rem;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  background: #0F172A;
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
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}

.sessions-list::-webkit-scrollbar-thumb:hover,
.messages-container::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>
