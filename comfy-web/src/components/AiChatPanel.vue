<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import AiChatComposer from '@/components/AiChatComposer.vue'
import AiBlobWarpAvatar from '@/components/AiBlobWarpAvatar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import { X, PlusIcon } from '@lucide/vue'
import { ElMessage, ElInputNumber } from 'element-plus'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Confirmation, ConfirmationRequest, ConfirmationActions, ConfirmationAction } from '@/components/ai-elements/confirmation'
import AssetPicker from '@/components/AssetPicker.vue'
import type { ChatSubmitData, AIModel } from '@/types/ai-models'
import {
  sendWorkflowMessageStream, getLanguageModels, getUserSessions,
  getSessionHistory, getTaskStatus, deleteSession,
  type WorkflowMessageRequest, type WorkflowMessageResponse, type WorkflowSession, type WorkflowTask,
  type ConversationMessage, type ChatAsset,
} from '@/api/workflow'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

type ChatMessage = ConversationMessage & { steps?: string[]; failed?: boolean }

const isProcessing = ref(false)
const messages = ref<ChatMessage[]>([])
const availableModels = ref<AIModel[]>([])
const isLoadingModels = ref(true)
const currentSessionId = ref<string | undefined>()
const activeTasks = ref<WorkflowTask[]>([])
const selectedAssets = ref<ChatAsset[]>([])
const assetPickerOpen = ref(false)
const generationType = ref<'none' | 'image' | 'video'>('none')
const generationModels = ref<Array<{ id: number; name: string; provider: string }>>([])
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
const messagesEl = ref<HTMLElement>()
let lastSubmitData: ChatSubmitData | undefined
let pollingTasks = false
let taskPoller: ReturnType<typeof setInterval> | undefined

const qualityLabels: Record<string, string> = { low: '低', medium: '中', high: '高' }
const parameterLabels: Record<string, string> = { n: '张数', aspect_ratio: '比例', quality: '质量', ratio: '比例', resolution: '分辨率', duration: '时长（秒）' }
const imageRatios = ['1:1', '16:9', '9:16', '4:3', '3:4'].map(v => ({ value: v, label: v }))
const videoRatios = ['16:9', '9:16', '1:1'].map(v => ({ value: v, label: v }))

function taskState(task: WorkflowTask) {
  if (task.status === 'completed') return 'output-available' as const
  if (task.status === 'failed') return 'output-error' as const
  return 'input-available' as const
}

function formatTime(dateStr: string) {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m}分钟前`
  const h = Math.floor(diff / 3600000)
  if (h < 24) return `${h}小时前`
  return `${Math.floor(diff / 86400000)}天前`
}

function buildAIModel(m: any): AIModel {
  const icon = ({ openai: 'openai', anthropic: 'anthropic', gemini: 'gemini', mistral: 'mistral' } as Record<string, AIModel['iconName']>)[m.provider.toLowerCase()] ?? 'openai'
  return { id: String(m.id), name: m.name, provider: m.provider, iconName: icon, badgeColor: 'text-emerald-500', accentColor: '#10a37f', reasoningTitle: '推理强度', defaultLevel: 'medium', levels: [{ id: 'medium', label: '中', desc: '平衡推理', multiplier: 2.6 }] }
}

async function loadLanguageModels() {
  try {
    isLoadingModels.value = true
    availableModels.value = (await getLanguageModels()).map(buildAIModel)
  } catch { ElMessage.error('模型加载失败，请刷新后重试。') }
  finally { isLoadingModels.value = false }
}

async function loadSessionDetail(sessionId: string) {
  try {
    const detail = await getSessionHistory(sessionId)
    if (currentSessionId.value !== sessionId) return
    messages.value = detail.conversations as ChatMessage[]
    activeTasks.value = detail.tasks || []
    if (detail.generation_request) openGenerationDialog(detail.generation_request)
  } catch { messages.value = []; activeTasks.value = [] }
}

function createNewSession() {
  if (isProcessing.value) return
  currentSessionId.value = undefined
  messages.value = []
  activeTasks.value = []
  selectedAssets.value = []
  generationType.value = 'none'
  generationDialogOpen.value = false
}

function selectAssets(assets: Array<{ id: number; location: string; asset_type?: string }>) {
  for (const a of assets) {
    if (selectedAssets.value.some(s => s.id === a.id) || selectedAssets.value.length >= 10) break
    selectedAssets.value.push({ id: a.id, asset_type: a.asset_type === 'video' ? 'video' : 'picture', url: `/api/api-proxy/output/${a.location.split(/[/\\]/).pop()}` })
  }
}

function openGenerationDialog(request: NonNullable<WorkflowMessageResponse['generation_request']>) {
  generationType.value = request.media_type
  generationModels.value = request.models
  pendingGenerationPrompt.value = request.prompt
  generationModelId.value = null
  imageCount.value = null; imageAspectRatio.value = null; imageQuality.value = null
  videoRatio.value = null; videoResolution.value = null; videoDuration.value = null
  generationDialogError.value = ''
  generationDialogOpen.value = true
}

async function confirmGeneration() {
  if (isProcessing.value) return
  const options: Parameters<typeof sendWorkflowMessageStream>[0]['generation_options'] = generationType.value === 'image'
    ? { media_type: 'image', model: generationModelId.value, n: imageCount.value, aspect_ratio: imageAspectRatio.value, quality: imageQuality.value }
    : { media_type: 'video', model: generationModelId.value, ratio: videoRatio.value, resolution: videoResolution.value, duration: videoDuration.value }
  if (Object.values(options ?? {}).some(v => v === null || v === undefined || v === '')) {
    generationDialogError.value = '请先选择模型，并填写全部生成参数。'
    return
  }
  const model = lastSubmitData?.model || availableModels.value[0]
  if (!model) { generationDialogError.value = '请先加载对话模型后重试。'; return }
  generationDialogOpen.value = false
  generationType.value = 'none'
  await handleSubmit({ prompt: pendingGenerationPrompt.value, model, useWebSearch: false, attachedFile: null }, options as any)
}

const conversationItems = computed(() => {
  const items: Array<{ key: string; type: 'message'; index: number; message: ChatMessage } | { key: string; type: 'task'; task: WorkflowTask }> = []
  for (const [index, msg] of messages.value.entries()) {
    items.push({ key: `msg-${msg.id ?? index}`, type: 'message', index, message: msg })
    if (msg.id != null)
      for (const task of activeTasks.value.filter(t => t.conversation_id === msg.id))
        items.push({ key: task.execution_id, type: 'task', task })
  }
  for (const task of activeTasks.value)
    if (task.conversation_id == null || !messages.value.some(m => m.id === task.conversation_id))
      items.push({ key: task.execution_id, type: 'task', task })
  return items
})

const handleSubmit = async (data: ChatSubmitData, confirmedOptions?: WorkflowMessageRequest['generation_options']) => {
  if (isProcessing.value) return
  lastSubmitData = data
  const submittedAssets = confirmedOptions ? [] : [...selectedAssets.value]

  messages.value.push({ role: 'user', message: data.prompt, assets: submittedAssets, created_at: new Date().toISOString() })
  const userMessage = messages.value[messages.value.length - 1]!
  messages.value.push({ role: 'agent', message: '', created_at: new Date().toISOString() })
  const agentMessage = messages.value[messages.value.length - 1]!

  isProcessing.value = true
  await nextTick(scrollToBottom)

  try {
    const response = await sendWorkflowMessageStream(
      { message: data.prompt, model_id: Number(data.model.id), session_id: currentSessionId.value, generation_options: confirmedOptions, asset_ids: submittedAssets.map(a => a.id) },
      (status) => {
        agentMessage.steps ??= []
        if (agentMessage.steps.at(-1) !== status) agentMessage.steps.push(status)
      },
      (text) => {
        const last = messages.value[messages.value.length - 1]
        if (last?.role === 'agent') last.message += text
        nextTick(scrollToBottom)
      },
      undefined,
      (usage) => { agentMessage.context_usage = usage },
    )
    agentMessage.context_usage = response.context_usage
    activeTasks.value = response.tasks || []
    if (!confirmedOptions) selectedAssets.value = []
    userMessage.id = response.user_conversation_id ?? undefined
    agentMessage.id = response.agent_conversation_id ?? undefined
    if (response.generation_request) openGenerationDialog(response.generation_request)

    const sessionChanged = Boolean(response.session_id && response.session_id !== currentSessionId.value)
    if (sessionChanged) currentSessionId.value = response.session_id

    if (agentMessage?.role === 'agent' && !agentMessage.message) agentMessage.message = response.reply

    if (response.workflow_ready && !sessionChanged) {
      await getUserSessions().catch(() => {})
    }
  } catch (error) {
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'agent') {
      last.failed = true
      last.message = error instanceof Error ? error.message : '抱歉，处理您的请求时出现错误。'
    }
  } finally {
    isProcessing.value = false
    nextTick(scrollToBottom)
  }
}

function scrollToBottom() {
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

async function pollTasksOnce() {
  if (pollingTasks || !currentSessionId.value) return
  const running = activeTasks.value.filter(t => t.status === 'running')
  if (!running.length) return
  pollingTasks = true
  const sid = currentSessionId.value
  try {
    for (const task of running) {
      try {
        const status = await getTaskStatus(task.task_id)
        if (sid !== currentSessionId.value) return
        if (status.status === 'completed' || status.status === 'failed') {
          const detail = await getSessionHistory(sid)
          if (sid !== currentSessionId.value) return
          activeTasks.value = detail.tasks || []
          break
        }
        task.stage = status.status
      } catch { /* 忽略单个任务查询失败 */ }
    }
  } finally { pollingTasks = false }
}

watch(() => props.modelValue, (open) => {
  if (open) nextTick(scrollToBottom)
})

onMounted(async () => {
  await loadLanguageModels()
  const sessions = await getUserSessions().catch(() => [] as WorkflowSession[])
  if (sessions.length > 0) {
    currentSessionId.value = sessions[0].id
    await loadSessionDetail(sessions[0].id)
  }
  taskPoller = setInterval(() => { void pollTasksOnce() }, 3000)
})

onUnmounted(() => { if (taskPoller) clearInterval(taskPoller) })
</script>

<template>
  <aside class="ai-panel" :class="{ open: modelValue }" aria-label="AI 助手面板">
    <header class="ai-panel-header">
      <div class="ai-panel-title">
        <AiBlobWarpAvatar class="panel-avatar" />
        <span>AI 助手</span>
      </div>
      <div class="ai-panel-actions">
        <button class="panel-btn" title="新建对话" :disabled="isProcessing" @click="createNewSession">
          <PlusIcon :size="15" />
        </button>
        <button class="panel-btn" title="关闭面板" @click="emit('update:modelValue', false)">
          <X :size="15" />
        </button>
      </div>
    </header>

    <div ref="messagesEl" class="ai-panel-messages">
      <div v-if="!messages.length" class="panel-welcome">
        <AiBlobWarpAvatar class="welcome-avatar" />
        <p>描述你想生成的图片或视频</p>
        <p class="panel-hint">支持图片、视频生成，以及提示词优化</p>
      </div>

      <template v-for="item in conversationItems" :key="item.key">
        <div v-if="item.type === 'message'" class="panel-msg" :data-role="item.message.role">
          <div class="msg-bubble">
            <div v-if="item.message.steps?.length" class="msg-steps">
              <span v-for="step in item.message.steps" :key="step" class="msg-step">{{ step }}</span>
            </div>
            <p v-if="item.message.message" :class="{ 'msg-error': item.message.failed }">
              {{ item.message.message }}
            </p>
            <p v-else-if="isProcessing && item.index === messages.length - 1" class="msg-thinking">●●●</p>
            <div v-if="item.message.assets?.length" class="msg-assets">
              <template v-for="asset in item.message.assets" :key="asset.id">
                <video v-if="asset.asset_type === 'video'" :src="asset.url" muted preload="metadata" />
                <img v-else :src="asset.url" alt="" loading="lazy" />
              </template>
            </div>
          </div>
          <span class="msg-time">{{ formatTime(item.message.created_at) }}</span>
        </div>

        <div v-else class="panel-task">
          <div class="task-header">
            <span class="task-label">{{ item.task.media_type === 'video' ? '视频生成' : '图片生成' }}</span>
            <span class="task-status" :data-state="taskState(item.task)">
              {{ item.task.status === 'completed' ? '完成' : item.task.status === 'failed' ? '失败' : item.task.stage || '处理中' }}
            </span>
          </div>
          <p v-if="item.task.parameters?.prompt" class="task-prompt">{{ item.task.parameters.prompt }}</p>
          <p v-if="item.task.status === 'failed'" class="task-error">{{ item.task.error || '生成失败，请调整后重试。' }}</p>
          <div v-if="item.task.images?.length || item.task.videos?.length" class="task-results">
            <a v-for="img in item.task.images" :key="img.asset_id" :href="img.url" target="_blank" rel="noreferrer">
              <img :src="img.url" alt="" loading="lazy" />
            </a>
            <video v-for="vid in (item.task.videos ?? [])" :key="vid.asset_id" :src="vid.url" controls />
          </div>
        </div>
      </template>
    </div>

    <div class="ai-panel-input">
      <div v-if="selectedAssets.length" class="panel-attachments">
        <div v-for="asset in selectedAssets" :key="asset.id" class="panel-asset">
          <video v-if="asset.asset_type === 'video'" :src="asset.url" muted preload="metadata" />
          <img v-else :src="asset.url" alt="" />
          <button class="asset-remove" :disabled="isProcessing" @click="selectedAssets = selectedAssets.filter(a => a.id !== asset.id)">×</button>
        </div>
      </div>
      <AiChatComposer
        :models="availableModels"
        :on-submit="handleSubmit"
        :is-processing="isProcessing"
        :asset-count="selectedAssets.length"
        @assets="assetPickerOpen = true"
      />
    </div>

    <Dialog v-model:open="generationDialogOpen">
      <DialogContent class="ai-elements generation-dialog" @interact-outside.prevent>
        <DialogHeader>
          <DialogTitle>{{ generationType === 'video' ? '确认视频生成' : '确认图片生成' }}</DialogTitle>
          <DialogDescription>检查提示词和参数，确认后开始生成。</DialogDescription>
        </DialogHeader>
        <Confirmation :approval="{ id: currentSessionId || 'gen' }" state="approval-requested" class="border-0 p-0">
          <ConfirmationRequest>
            <p class="generation-prompt">{{ pendingGenerationPrompt }}</p>
            <div class="generation-fields">
              <div class="gen-field">
                <span>生成模型</span>
                <Select :model-value="generationModelId == null ? undefined : String(generationModelId)" @update:model-value="generationModelId = $event ? Number($event) : null">
                  <SelectTrigger class="w-full"><SelectValue placeholder="选择生成模型" /></SelectTrigger>
                  <SelectContent class="ai-elements">
                    <SelectItem v-for="m in generationModels" :key="m.id" :value="String(m.id)">{{ m.name }} · {{ m.provider }}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <template v-if="generationType === 'image'">
                <div class="gen-field"><span>画面比例</span><SegmentedControl :model-value="imageAspectRatio || ''" :options="imageRatios" label="图片比例" @update:model-value="imageAspectRatio = $event" /></div>
                <div class="gen-field"><span>图片质量</span><SegmentedControl :model-value="imageQuality || ''" :options="[{value:'low',label:'低'},{value:'medium',label:'中'},{value:'high',label:'高'}]" label="图片质量" @update:model-value="imageQuality = $event" /></div>
                <label>生成张数<ElInputNumber v-model="imageCount" :min="1" :max="10" /></label>
              </template>
              <template v-else>
                <div class="gen-field"><span>画面比例</span><SegmentedControl :model-value="videoRatio || ''" :options="videoRatios" label="视频比例" @update:model-value="videoRatio = $event" /></div>
                <div class="gen-field"><span>分辨率</span><SegmentedControl :model-value="videoResolution || ''" :options="[{value:'720p',label:'720p'},{value:'1080p',label:'1080p'}]" label="分辨率" @update:model-value="videoResolution = $event" /></div>
                <label>视频时长（秒）<ElInputNumber v-model="videoDuration" :min="1" :max="60" /></label>
              </template>
              <p v-if="generationDialogError" role="alert" class="task-error">{{ generationDialogError }}</p>
            </div>
          </ConfirmationRequest>
          <ConfirmationActions>
            <ConfirmationAction variant="outline" @click="generationDialogOpen = false">稍后确认</ConfirmationAction>
            <ConfirmationAction :disabled="isProcessing" @click="confirmGeneration">确认并生成</ConfirmationAction>
          </ConfirmationActions>
        </Confirmation>
      </DialogContent>
    </Dialog>

    <AssetPicker v-model:visible="assetPickerOpen" :max-select="10 - selectedAssets.length" allow-video @select="selectAssets" />
  </aside>
</template>

<style scoped>
.ai-panel {
  position: fixed;
  right: 0;
  top: 0;
  height: 100vh;
  width: 380px;
  display: flex;
  flex-direction: column;
  background: rgba(var(--color-surface-rgb), 0.92);
  backdrop-filter: blur(20px) saturate(130%);
  border-left: 1px solid var(--color-border);
  z-index: 150;
  transform: translateX(100%);
  transition: transform 0.3s cubic-bezier(0.22, 1, 0.36, 1);
  box-shadow: -8px 0 32px rgba(0,0,0,0.18);
}
.ai-panel.open { transform: translateX(0); }

.ai-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.ai-panel-title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 500; }
.panel-avatar { width: 24px; height: 24px; }
.ai-panel-actions { display: flex; gap: 4px; }
.panel-btn {
  display: grid; place-items: center;
  width: 28px; height: 28px;
  border: 0; border-radius: 6px;
  background: transparent; color: var(--color-muted);
  cursor: pointer; transition: background 0.15s, color 0.15s;
}
.panel-btn:hover { background: rgba(var(--color-white-rgb), 0.08); color: var(--color-text); }
.panel-btn:disabled { opacity: 0.4; cursor: default; }

.ai-panel-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  scroll-behavior: smooth;
}

.panel-welcome {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 10px; flex: 1;
  text-align: center; padding: 40px 20px; color: var(--color-muted);
}
.welcome-avatar { width: 36px; height: 36px; margin-bottom: 4px; }
.panel-welcome p { font-size: 14px; }
.panel-hint { font-size: 12px; opacity: 0.6; }

.panel-msg { display: flex; flex-direction: column; gap: 4px; }
.panel-msg[data-role="user"] { align-items: flex-end; }
.panel-msg[data-role="agent"] { align-items: flex-start; }

.msg-bubble {
  max-width: 88%;
  padding: 10px 13px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
}
.panel-msg[data-role="user"] .msg-bubble {
  background: var(--color-primary);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.panel-msg[data-role="agent"] .msg-bubble {
  background: rgba(var(--color-white-rgb), 0.07);
  border-bottom-left-radius: 4px;
}
.msg-steps { display: flex; flex-direction: column; gap: 2px; margin-bottom: 6px; }
.msg-step { font-size: 11px; color: var(--color-muted); }
.msg-thinking { letter-spacing: 4px; animation: blink 1.2s infinite; }
@keyframes blink { 0%,100%{opacity:0.3} 50%{opacity:1} }
.msg-error { color: var(--color-danger) !important; }
.msg-assets { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.msg-assets img, .msg-assets video { max-width: 100px; max-height: 80px; border-radius: 6px; object-fit: cover; }
.msg-time { font-size: 10px; color: var(--color-muted); opacity: 0.6; padding: 0 4px; }

.panel-task {
  background: rgba(var(--color-white-rgb), 0.05);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 12px;
  font-size: 12px;
}
.task-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.task-label { font-weight: 500; font-size: 12px; }
.task-status { font-size: 11px; color: var(--color-muted); }
.task-status[data-state="output-available"] { color: var(--color-success, #22c55e); }
.task-status[data-state="output-error"] { color: var(--color-danger); }
.task-prompt { color: var(--color-muted); font-size: 12px; line-height: 1.5; margin-bottom: 6px; }
.task-error { color: var(--color-danger); font-size: 12px; margin-top: 4px; }
.task-results { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.task-results img, .task-results video { max-width: 100%; border-radius: 6px; }
.task-results a { display: block; }

.ai-panel-input {
  border-top: 1px solid var(--color-border);
  padding: 10px 12px 12px;
  flex-shrink: 0;
  background: rgba(var(--color-surface-rgb), 0.6);
}
.panel-attachments { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.panel-asset { position: relative; }
.panel-asset img, .panel-asset video { width: 48px; height: 48px; object-fit: cover; border-radius: 6px; }
.asset-remove {
  position: absolute; top: -4px; right: -4px;
  width: 16px; height: 16px;
  border-radius: 50%; border: 0;
  background: var(--color-danger); color: #fff;
  font-size: 11px; cursor: pointer;
  display: grid; place-items: center; line-height: 1;
}

.generation-prompt { font-size: 13px; line-height: 1.6; margin-bottom: 14px; color: var(--color-text); }
.generation-fields { display: flex; flex-direction: column; gap: 12px; }
.gen-field { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--color-muted); }
</style>
