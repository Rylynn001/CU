<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import AiChatComposer from '@/components/AiChatComposer.vue'
import AiExecutionTrace from '@/components/AiExecutionTrace.vue'
import AiBlobWarpAvatar from '@/components/AiBlobWarpAvatar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import { X, PlusIcon, Image, Video, LoaderCircle, CircleCheck, CircleAlert, History } from '@lucide/vue'
import { ElMessage, ElInputNumber } from 'element-plus'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Confirmation, ConfirmationRequest, ConfirmationActions, ConfirmationAction } from '@/components/ai-elements/confirmation'
import AssetPicker from '@/components/AssetPicker.vue'
import type { ChatSubmitData, AIModel } from '@/types/ai-models'
import type { CanvasReference } from '@/services/canvasGraph'
import {
  sendWorkflowMessageStream, getLanguageModels, getUserSessions,
  getSessionHistory, retryGenerationPlan,
  type WorkflowMessageRequest, type WorkflowMessageResponse, type WorkflowSession, type WorkflowTask,
  type ConversationMessage, type ChatAsset, type GenerationRequest,
} from '@/api/workflow'

const props = defineProps<{ modelValue: boolean; canvasId: number; prepareCanvas: () => Promise<void>; references?: CanvasReference[] }>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; 'canvas-changed': [number]; 'busy-change': [boolean] }>()

type ChatMessage = ConversationMessage & { steps?: string[]; failed?: boolean }

const isProcessing = ref(false)
const messages = ref<ChatMessage[]>([])
const availableModels = ref<AIModel[]>([])
const isLoadingModels = ref(true)
const currentSessionId = ref<string | undefined>()
const sessions = ref<WorkflowSession[]>([])
const historyOpen = ref(false)
const loadingSession = ref(false)
const historyError = ref('')
const activeTasks = ref<WorkflowTask[]>([])
const selectedAssets = ref<ChatAsset[]>([])
const assetPickerOpen = ref(false)
const referenceItems = computed(() => {
  const items = new Map((props.references ?? []).map(item => [item.id, item]))
  for (const asset of selectedAssets.value) {
    if (items.has(asset.id)) continue
    const type = asset.asset_type === 'video' ? 'video' : 'image'
    items.set(asset.id, { id: asset.id, url: asset.url, type, label: type === 'video' ? '视频素材' : '图片素材', referenceId: 0, mention: `@${type === 'video' ? '视频' : '图片'}${asset.id}` })
  }
  const counters = { image: 0, video: 0 }
  return [...items.values()].map(item => {
    const referenceId = ++counters[item.type]
    return { ...item, referenceId, mention: `@${item.type === 'video' ? '视频' : '图片'}${referenceId}` }
  })
})
const pendingPlan = ref<Extract<GenerationRequest, { media_type: 'plan' }> | null>(null)
const planOptions = ref<Partial<Record<'image' | 'video', Record<string, unknown>>>>({})
const retryingPlan = ref<string | null>(null)
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
  loadingSession.value = true
  generationDialogOpen.value = false
  pendingPlan.value = null
  try {
    const detail = await getSessionHistory(sessionId, props.canvasId)
    if (currentSessionId.value !== sessionId) return
    messages.value = detail.conversations as ChatMessage[]
    activeTasks.value = detail.tasks || []
    if (detail.generation_request) openGenerationDialog(detail.generation_request)
  } catch { ElMessage.error('会话加载失败，请重试') }
  finally { loadingSession.value = false }
}

async function loadSessions() {
  historyError.value = ''
  try { sessions.value = await getUserSessions(props.canvasId) }
  catch (error) { historyError.value = error instanceof Error ? error.message : '历史窗口加载失败' }
}

async function selectSession(sessionId: string) {
  if (isProcessing.value || loadingSession.value) return
  createNewSession()
  currentSessionId.value = sessionId
  historyOpen.value = false
  await loadSessionDetail(sessionId)
}

async function showHistory() {
  historyOpen.value = true
  await loadSessions()
}

function createNewSession() {
  if (isProcessing.value || loadingSession.value) return
  currentSessionId.value = undefined
  messages.value = []
  activeTasks.value = []
  selectedAssets.value = []
  generationType.value = 'none'
  generationDialogOpen.value = false
  pendingPlan.value = null
}

function selectAssets(assets: Array<{ id: number; location: string; asset_type?: string }>) {
  for (const a of assets) {
    if (selectedAssets.value.some(s => s.id === a.id) || selectedAssets.value.length >= 10) break
    selectedAssets.value.push({ id: a.id, asset_type: a.asset_type === 'video' ? 'video' : 'picture', url: `/api/api-proxy/output/${a.location.split(/[/\\]/).pop()}` })
  }
}

function resetGenerationFields(type: 'image' | 'video') {
  generationType.value = type
  generationModels.value = pendingPlan.value?.models_by_type[type] ?? []
  generationModelId.value = null
  imageCount.value = pendingPlan.value ? 1 : null
  imageAspectRatio.value = null; imageQuality.value = null
  videoRatio.value = null; videoResolution.value = null
  videoDuration.value = pendingPlan.value?.steps.find(step => step.media_type === 'video')?.duration ?? null
  generationDialogError.value = ''
}

function openGenerationDialog(request: NonNullable<WorkflowMessageResponse['generation_request']>) {
  pendingPlan.value = request.media_type === 'plan' ? request : null
  planOptions.value = {}
  pendingGenerationPrompt.value = request.prompt
  resetGenerationFields(request.media_type === 'plan' ? request.steps[0]!.media_type : request.media_type)
  if (request.media_type !== 'plan') generationModels.value = request.models
  generationDialogOpen.value = true
}

const hasNextPlanParameters = computed(() => pendingPlan.value?.steps.some(step =>
  step.media_type !== generationType.value && !planOptions.value[step.media_type]))
const fixedVideoDuration = computed(() => {
  const steps = pendingPlan.value?.steps.filter(step => step.media_type === 'video')
  return !!steps?.length && steps.every(step => step.duration != null)
})

async function confirmGeneration() {
  if (isProcessing.value) return
  const options = generationType.value === 'image'
    ? { media_type: 'image' as const, model: generationModelId.value, n: imageCount.value, aspect_ratio: imageAspectRatio.value, quality: imageQuality.value }
    : { media_type: 'video' as const, model: generationModelId.value, ratio: videoRatio.value, resolution: videoResolution.value, duration: videoDuration.value }
  if (Object.values(options).some(v => v === null || v === undefined || v === '')) {
    generationDialogError.value = '请先选择模型，并填写全部生成参数。'
    return
  }
  const model = lastSubmitData?.model || availableModels.value[0]
  if (!model) { generationDialogError.value = '请先加载对话模型后重试。'; return }
  let confirmed: WorkflowMessageRequest['generation_options'] = options
  if (pendingPlan.value) {
    planOptions.value[options.media_type] = options
    const next = pendingPlan.value.steps.find(step => !planOptions.value[step.media_type])
    if (next) { resetGenerationFields(next.media_type); return }
    confirmed = { media_type: 'plan', plan_id: pendingPlan.value.plan_id, ...planOptions.value }
  }
  generationDialogOpen.value = false
  generationType.value = 'none'
  await handleSubmit({ prompt: pendingGenerationPrompt.value, model, useWebSearch: false, attachedFile: null }, confirmed)
}

function canRetryPlan(task: WorkflowTask) {
  return task.status === 'failed' && task.plan_id && !activeTasks.value.some(item =>
    item.plan_id === task.plan_id && ['running', 'queued', 'submitting'].includes(item.status))
    && activeTasks.value.find(item => item.plan_id === task.plan_id && item.status === 'failed') === task
}

async function retryPlan(task: WorkflowTask) {
  if (!task.plan_id || !currentSessionId.value || retryingPlan.value) return
  const sid = currentSessionId.value
  retryingPlan.value = task.plan_id
  try {
    await retryGenerationPlan(task.plan_id, props.canvasId)
    const detail = await getSessionHistory(sid, props.canvasId)
    if (currentSessionId.value === sid) activeTasks.value = detail.tasks || []
    emit('canvas-changed', props.canvasId)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '重试失败') }
  finally { retryingPlan.value = null }
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
  if (isProcessing.value || loadingSession.value) return
  lastSubmitData = data
  const submittedAssets = confirmedOptions ? [] : [...selectedAssets.value]
  if (!confirmedOptions) {
    for (const match of data.prompt.matchAll(/@(图|图片|视频)(\d+)/g)) {
      const type = match[1] === '视频' ? 'video' : 'image'
      const item = referenceItems.value.filter(item => item.type === type)[Number(match[2]) - 1]
      if (!item?.url) { ElMessage.warning(`引用 ${match[0]} 已不可用，请重新选择素材`); return }
      if (!submittedAssets.some(asset => asset.id === item.id)) submittedAssets.push({ id: item.id, url: item.url, asset_type: item.type === 'video' ? 'video' : 'picture' })
    }
    if (submittedAssets.length > 10) { ElMessage.warning('每条消息最多引用 10 个素材'); return }
  }

  messages.value.push({ role: 'user', message: data.prompt, assets: submittedAssets, created_at: new Date().toISOString() })
  const userMessage = messages.value[messages.value.length - 1]!
  messages.value.push({ role: 'agent', message: '', created_at: new Date().toISOString() })
  const agentMessage = messages.value[messages.value.length - 1]!

  isProcessing.value = true
  emit('busy-change', true)
  await nextTick(scrollToBottom)

  try {
    await props.prepareCanvas()
    const response = await sendWorkflowMessageStream(
      { canvas_id: props.canvasId, message: data.prompt, model_id: Number(data.model.id), session_id: currentSessionId.value, generation_options: confirmedOptions, asset_ids: submittedAssets.map(a => a.id) },
      (status) => {
        agentMessage.steps ??= []
        if (agentMessage.steps.at(-1) !== status) agentMessage.steps.push(status)
        nextTick(scrollToBottom)
      },
      (text) => {
        if (typeof text !== 'string') return
        agentMessage.message += text
        nextTick(scrollToBottom)
      },
      (event) => {
        agentMessage.events ??= []
        agentMessage.events.push(event)
        nextTick(scrollToBottom)
      },
      (usage) => { agentMessage.context_usage = usage },
      (canvasId) => emit('canvas-changed', canvasId),
    )
    agentMessage.context_usage = response.context_usage
    activeTasks.value = response.tasks || []
    if (!confirmedOptions) selectedAssets.value = []
    userMessage.id = response.user_conversation_id ?? undefined
    agentMessage.id = response.agent_conversation_id ?? undefined
    if (response.generation_request) openGenerationDialog(response.generation_request)
    else if (response.workflow_ready) pendingPlan.value = null

    const sessionChanged = Boolean(response.session_id && response.session_id !== currentSessionId.value)
    if (sessionChanged) currentSessionId.value = response.session_id

    agentMessage.message = response.reply

    await loadSessions()
  } catch (error) {
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'agent') {
      last.failed = true
      last.message = error instanceof Error ? error.message : '抱歉，处理您的请求时出现错误。'
    }
  } finally {
    isProcessing.value = false
    emit('busy-change', false)
    emit('canvas-changed', props.canvasId)
    nextTick(scrollToBottom)
  }
}

function scrollToBottom() {
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

async function pollTasksOnce() {
  if (pollingTasks || !currentSessionId.value) return
  if (!activeTasks.value.some(task => ['running', 'queued', 'submitting'].includes(task.status))) return
  pollingTasks = true
  const sid = currentSessionId.value
  try {
    const detail = await getSessionHistory(sid, props.canvasId)
    if (sid !== currentSessionId.value) return
    activeTasks.value = detail.tasks || []
  } catch { /* 保留最近一次进度，下次轮询重试 */ }
  finally { pollingTasks = false }
}

watch(() => props.modelValue, (open) => {
  if (open) nextTick(scrollToBottom)
})

onMounted(async () => {
  void loadLanguageModels()
  loadingSession.value = true
  await loadSessions()
  if (sessions.value.length > 0) {
    currentSessionId.value = sessions.value[0]!.id
    await loadSessionDetail(sessions.value[0]!.id)
  }
  loadingSession.value = false
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
        <button class="panel-btn" title="当前画布的历史窗口" aria-label="当前画布的历史窗口" :disabled="isProcessing || loadingSession" @click="showHistory">
          <History :size="15" />
        </button>
        <button class="panel-btn" title="新建对话" :disabled="isProcessing || loadingSession" @click="createNewSession">
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
            <AiExecutionTrace
              v-if="item.message.role === 'agent' && (item.message.events?.length || item.message.steps?.length || (isProcessing && item.index === messages.length - 1))"
              :events="item.message.events"
              :steps="item.message.steps"
              :processing="isProcessing && item.index === messages.length - 1"
              :failed="item.message.failed"
            />
            <p v-if="item.message.message" :class="{ 'msg-error': item.message.failed }">
              {{ item.message.message }}
            </p>
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
            <span class="task-label"><Video v-if="item.task.media_type === 'video'" :size="15" /><Image v-else :size="15" />{{ item.task.label || (item.task.media_type === 'video' ? '视频生成' : '图片生成') }}</span>
            <span class="task-status" :data-state="taskState(item.task)">
              <CircleCheck v-if="item.task.status === 'completed'" :size="13" />
              <CircleAlert v-else-if="item.task.status === 'failed'" :size="13" />
              <LoaderCircle v-else :size="13" class="task-spinner" />
              {{ item.task.status === 'completed' ? '完成' : item.task.status === 'failed' ? '失败' : item.task.stage || '处理中' }}
            </span>
          </div>
          <p v-if="item.task.model_name" class="task-model">{{ item.task.model_name }}</p>
          <p v-if="item.task.parameters?.prompt" class="task-prompt">{{ item.task.parameters.prompt }}</p>
          <p v-if="item.task.status === 'failed'" class="task-error">{{ item.task.error || '生成失败，请调整后重试。' }}</p>
          <Button v-if="canRetryPlan(item.task)" variant="outline" :disabled="!!retryingPlan" @click="retryPlan(item.task)">重试失败步骤</Button>
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
      <Button v-if="pendingPlan && !generationDialogOpen" variant="outline" :disabled="isProcessing || loadingSession" @click="openGenerationDialog(pendingPlan)">继续确认任务计划</Button>
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
        :is-processing="isProcessing || loadingSession"
        :asset-count="selectedAssets.length"
        :references="referenceItems"
        @assets="assetPickerOpen = true"
      />
    </div>

    <Dialog v-model:open="historyOpen">
      <DialogContent class="ai-elements history-dialog">
        <DialogHeader>
          <DialogTitle>画布历史窗口</DialogTitle>
          <DialogDescription>查看和继续当前画布的会话。</DialogDescription>
        </DialogHeader>
        <p v-if="historyError" role="alert" class="task-error">{{ historyError }}</p>
        <p v-else-if="!sessions.length" class="history-empty">当前画布还没有历史会话。</p>
        <div class="history-list">
          <Button v-for="session in sessions" :key="session.id" variant="ghost" class="history-item"
            :aria-current="session.id === currentSessionId ? 'true' : undefined"
            :disabled="isProcessing || loadingSession" @click="selectSession(session.id)">
            <span class="history-title">{{ session.title || '新会话' }}</span>
            <span class="history-time">{{ formatTime(session.updated_at) }}{{ session.id === currentSessionId ? ' · 当前窗口' : '' }}</span>
          </Button>
        </div>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="generationDialogOpen">
      <DialogContent class="ai-elements generation-dialog" @interact-outside.prevent>
        <DialogHeader>
          <DialogTitle>{{ generationType === 'video' ? '确认视频生成' : '确认图片生成' }}</DialogTitle>
          <DialogDescription>{{ pendingPlan ? `共 ${pendingPlan.steps.length} 个步骤。分别确认图片和视频参数后，开始整个任务。` : '检查提示词和参数，确认后开始生成。' }}</DialogDescription>
        </DialogHeader>
        <Confirmation :approval="{ id: currentSessionId || 'gen' }" state="approval-requested" class="generation-confirmation border-0 p-0">
          <ConfirmationRequest>
            <ol v-if="pendingPlan" class="generation-plan">
              <li v-for="step in pendingPlan.steps" :key="step.id">
                <strong>{{ step.label }}{{ step.duration ? ` · ${step.duration} 秒` : '' }}</strong>
                <p>{{ step.prompt }}</p>
                <small v-if="step.depends_on.length">等待：{{ step.depends_on.map(id => pendingPlan?.steps.find(item => item.id === id)?.label).join('、') }}</small>
              </li>
            </ol>
            <p v-else class="generation-prompt">{{ pendingGenerationPrompt }}</p>
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
                <label>{{ pendingPlan ? '每步生成张数' : '生成张数' }}<ElInputNumber v-model="imageCount" :min="1" :max="10" :disabled="!!pendingPlan" /></label>
              </template>
              <template v-else>
                <div class="gen-field"><span>画面比例</span><SegmentedControl :model-value="videoRatio || ''" :options="videoRatios" label="视频比例" @update:model-value="videoRatio = $event" /></div>
                <div class="gen-field"><span>分辨率</span><SegmentedControl :model-value="videoResolution || ''" :options="[{value:'720p',label:'720p'},{value:'1080p',label:'1080p'}]" label="分辨率" @update:model-value="videoResolution = $event" /></div>
                <label>视频时长（秒）<ElInputNumber v-model="videoDuration" :min="1" :max="60" :disabled="fixedVideoDuration" /></label>
                <p v-if="pendingPlan" class="task-model">已指定时长的步骤按计划执行，此处时长用于其余视频步骤。</p>
              </template>
              <p v-if="generationDialogError" role="alert" class="task-error">{{ generationDialogError }}</p>
            </div>
          </ConfirmationRequest>
          <ConfirmationActions>
            <ConfirmationAction variant="outline" @click="generationDialogOpen = false">稍后确认</ConfirmationAction>
            <ConfirmationAction :disabled="isProcessing" @click="confirmGeneration">{{ hasNextPlanParameters ? '下一步：确认其他生成参数' : pendingPlan ? `确认并执行 ${pendingPlan.steps.length} 步` : '确认并生成' }}</ConfirmationAction>
          </ConfirmationActions>
        </Confirmation>
      </DialogContent>
    </Dialog>

    <AssetPicker v-model:visible="assetPickerOpen" :max-select="10 - selectedAssets.length" allow-video @select="selectAssets" />
  </aside>
</template>

<style scoped>
.history-dialog { max-width: 440px; }
.history-list { display: flex; flex-direction: column; gap: 4px; max-height: 55vh; overflow-y: auto; }
.history-item { height: auto; align-items: flex-start; flex-direction: column; gap: 4px; padding: 12px; text-align: left; }
.history-item[aria-current="true"] { background: var(--color-surface-soft); }
.history-title { width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-text); }
.history-time, .history-empty { font-size: 12px; color: var(--color-muted); }
.ai-panel {
  position: fixed;
  right: 0;
  bottom: 0;
  height: min(720px, calc(100dvh - 72px));
  width: min(400px, 100vw);
  display: flex;
  flex-direction: column;
  background: rgba(var(--color-surface-rgb), 0.92);
  backdrop-filter: blur(20px) saturate(130%);
  border: 1px solid var(--color-border);
  border-radius: 20px 0 0 0;
  border-right: 0;
  border-bottom: 0;
  z-index: 40;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transform: translateY(16px) scale(.97);
  transform-origin: bottom right;
  transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), opacity .2s ease, visibility .2s;
  box-shadow: 0 24px 70px rgba(0,0,0,0.34);
}
.ai-panel.open { opacity: 1; visibility: visible; pointer-events: auto; transform: translateY(0) scale(1); }

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
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 20px 18px;
  display: flex;
  flex-direction: column;
  gap: 20px;
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
  min-width: 0;
  max-width: 88%;
  padding: 10px 13px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.msg-bubble > p { white-space: pre-wrap; }
.panel-msg[data-role="user"] .msg-bubble {
  background: rgba(var(--color-info-rgb), 0.16);
  border: 1px solid rgba(var(--color-info-rgb), 0.24);
  color: var(--color-text);
  border-bottom-right-radius: 4px;
}
.panel-msg[data-role="agent"] .msg-bubble {
  width: 100%;
  max-width: 100%;
  padding: 0;
  background: transparent;
}
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
.task-label { display: flex; align-items: center; gap: 7px; font-weight: 500; font-size: 12px; }
.task-status { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--color-muted); }
.task-model { margin-bottom: 6px; font-size: 11px; color: var(--color-muted); }
.task-spinner { animation: task-spin 1s linear infinite; }
@keyframes task-spin { to { transform: rotate(360deg); } }
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
.ai-panel-input :deep(textarea) { min-height: 72px; padding: 12px 14px; font-size: 13px; }
.ai-panel-input :deep(.composer-footnote) { margin-top: 7px; font-size: 10px; }
.ai-panel-input :deep([data-slot="select-trigger"]) { max-width: 160px; }
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

.generation-confirmation { display: flex; flex-direction: column; align-items: stretch; min-width: 0; }
.generation-plan { margin: 0 0 14px; padding-left: 22px; max-height: 28vh; overflow-y: auto; overflow-wrap: anywhere; color: var(--color-text); font-size: 13px; }
.generation-plan li { margin-bottom: 10px; }
.generation-plan p, .generation-plan small { color: var(--color-muted); }
.generation-prompt { font-size: 13px; line-height: 1.6; margin-bottom: 14px; color: var(--color-text); }
.generation-fields { display: flex; flex-direction: column; gap: 12px; }
.gen-field { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--color-muted); }

@media (max-width: 600px) {
  .ai-panel { width: 100vw; height: min(660px, calc(100dvh - 56px)); border-radius: 18px 0 0 0; }
  .ai-panel-input { padding-bottom: max(12px, env(safe-area-inset-bottom)); }
}
@media (prefers-reduced-motion: reduce) {
  .ai-panel { transition: none; }
  .ai-panel-messages { scroll-behavior: auto; }
  .task-spinner { animation: none; }
}
</style>
