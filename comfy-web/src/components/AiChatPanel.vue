<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import AiChatComposer from '@/components/AiChatComposer.vue'
import ChatSkillPicker from '@/components/ChatSkillPicker.vue'
import AiExecutionTrace from '@/components/AiExecutionTrace.vue'
import AiBlobWarpAvatar from '@/components/AiBlobWarpAvatar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import { IMAGE_ASPECT_RATIOS, VIDEO_ASPECT_RATIOS } from '@/constants/aspectRatios'
import { X, PlusIcon, Image, Video, LoaderCircle, CircleCheck, CircleAlert, History, Folder, MoreVertical, Pencil, Trash2, ExternalLink } from '@lucide/vue'
import { ElMessage, ElInputNumber, ElSlider } from 'element-plus'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '@/components/ui/dropdown-menu'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Confirmation, ConfirmationRequest, ConfirmationActions, ConfirmationAction } from '@/components/ai-elements/confirmation'
import AssetPicker from '@/components/AssetPicker.vue'
import type { ChatSubmitData, AIModel } from '@/types/ai-models'
import type { CanvasReference, PromptOptimizationTarget } from '@/services/canvasGraph'
import type { CanvasSummary } from '@/api/apiService'
import {
  sendWorkflowMessageStream, getLanguageModels, getUserSessions, getChatSkills,
  getSessionHistory, retryGenerationPlan,
  type WorkflowMessageRequest, type WorkflowMessageResponse, type WorkflowSession, type WorkflowTask,
  type ConversationMessage, type ChatAsset, type GenerationRequest, type GenerationModel, type ChatSkill,
} from '@/api/workflow'

const props = defineProps<{ modelValue: boolean; canvasId?: number; prepareCanvas: (name?: string) => Promise<number | void>; references?: CanvasReference[]; boards?: CanvasSummary[]; homeMode?: boolean; homeLoading?: boolean; homeError?: string; renameCanvas?: (id: number, name: string) => Promise<void>; deleteCanvas?: (id: number) => Promise<void>; createCanvas?: (name: string) => Promise<void> }>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; 'canvas-changed': [number]; 'busy-change': [boolean]; 'select-canvas': [number | undefined]; 'open-canvas': [number]; 'create-canvas': []; 'apply-prompt': [target: PromptOptimizationTarget, prompt: string] }>()

type ChatMessage = ConversationMessage & { steps?: string[]; failed?: boolean; stopped?: boolean; optimizedPrompt?: string }

const isProcessing = ref(false)
const canStop = ref(false)
let chatController: AbortController | undefined

function stopProcessing() {
  chatController?.abort()
  canStop.value = false
}
const messages = ref<ChatMessage[]>([])
const contextUsage = computed(() => [...messages.value].reverse().find(message => message.context_usage)?.context_usage)
const availableModels = ref<AIModel[]>([])
const isLoadingModels = ref(true)
const skills = ref<ChatSkill[]>([])
const selectedSkillId = ref('')
const skillsLoading = ref(false)
const skillsError = ref('')
const optimizationTarget = ref<PromptOptimizationTarget>()

async function loadSkills() {
  if (skillsLoading.value) return
  skillsLoading.value = true
  skillsError.value = ''
  try {
    skills.value = await getChatSkills()
    if (selectedSkillId.value && !skills.value.some(skill => skill.id === selectedSkillId.value)) {
      selectedSkillId.value = ''
      ElMessage.info('原先选择的技能已移除，请重新选择')
    }
  } catch (error) { skillsError.value = error instanceof Error ? error.message : '技能列表加载失败' }
  finally { skillsLoading.value = false }
}
const currentSessionId = ref<string | undefined>()
const sessions = ref<WorkflowSession[]>([])
const historyOpen = ref(false)
const loadingSession = ref(false)
const historyError = ref('')
const activeTasks = ref<WorkflowTask[]>([])
const selectedAssets = ref<ChatAsset[]>([])
const assetPickerOpen = ref(false)
const referenceItems = computed(() => {
  const items = new Map((optimizationTarget.value?.references ?? props.references ?? []).map(item => [item.id, item]))
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
const generationModels = ref<GenerationModel[]>([])
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
const composer = ref<InstanceType<typeof AiChatComposer>>()
type CanvasDialog = { type: 'create'; submission?: ChatSubmitData } | { type: 'rename' | 'delete'; board: CanvasSummary }
const canvasDialog = ref<CanvasDialog>()
const canvasName = ref('')
const canvasDialogBusy = ref(false)
const canvasDialogError = ref('')
const canvasDialogOpen = computed({
  get: () => !!canvasDialog.value,
  set: open => { if (!open && !canvasDialogBusy.value) canvasDialog.value = undefined },
})

function openCanvasDialog(type: 'rename' | 'delete', board: CanvasSummary) {
  canvasName.value = board.name
  canvasDialogError.value = ''
  canvasDialog.value = { type, board }
}

function openCreateCanvasDialog() {
  canvasName.value = ''
  canvasDialogError.value = ''
  canvasDialog.value = { type: 'create' }
}

async function confirmCanvasDialog() {
  const dialog = canvasDialog.value
  if (!dialog || canvasDialogBusy.value) return
  const nextName = canvasName.value.trim()
  if (dialog.type !== 'delete' && !nextName) { canvasDialogError.value = '请输入画布名称'; return }
  if (dialog.type === 'create') {
    if (dialog.submission) {
      canvasDialog.value = undefined
      await handleSubmit(dialog.submission, undefined, nextName)
      return
    }
    canvasDialogBusy.value = true
    canvasDialogError.value = ''
    try {
      await props.createCanvas?.(nextName)
      canvasDialog.value = undefined
    } catch (error) { canvasDialogError.value = error instanceof Error ? error.message : '操作失败，请重试' }
    finally { canvasDialogBusy.value = false }
    return
  }
  canvasDialogBusy.value = true
  canvasDialogError.value = ''
  try {
    if (dialog.type === 'rename') await props.renameCanvas?.(dialog.board.id, nextName)
    else await props.deleteCanvas?.(dialog.board.id)
    canvasDialog.value = undefined
  } catch (error) { canvasDialogError.value = error instanceof Error ? error.message : '操作失败，请重试' }
  finally { canvasDialogBusy.value = false }
}
let lastSubmitData: ChatSubmitData | undefined
let pollingTasks = false
let taskPoller: ReturnType<typeof setInterval> | undefined

const qualityLabels: Record<string, string> = { low: '低', medium: '中', high: '高' }
const parameterLabels: Record<string, string> = { n: '张数', aspect_ratio: '比例', quality: '质量', resolution: '分辨率', duration: '时长（秒）' }
const imageRatios = IMAGE_ASPECT_RATIOS
const videoRatios = VIDEO_ASPECT_RATIOS

const videoResolutionOptions = computed(() => {
  const field = generationModels.value
    .find(model => model.id === generationModelId.value)
    ?.parameters?.fields?.find(field => field.key === 'resolution')
  const options = field?.options?.map(value => String(value)) ?? ['480p', '720p', '1080p', '4k']
  return options.map(value => ({ value, label: value.toLowerCase() === '4k' ? '4K' : value }))
})

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
  return { id: String(m.id), name: m.name, provider: m.provider, contextWindow: m.context_window, iconName: icon, badgeColor: 'text-emerald-500', accentColor: '#10a37f', reasoningTitle: '推理强度', defaultLevel: 'medium', levels: [{ id: 'medium', label: '中', desc: '平衡推理', multiplier: 2.6 }] }
}

async function loadLanguageModels() {
  try {
    isLoadingModels.value = true
    availableModels.value = (await getLanguageModels()).map(buildAIModel)
  } catch { ElMessage.error('模型加载失败，请刷新后重试。') }
  finally { isLoadingModels.value = false }
}

async function loadSessionDetail(sessionId: string, canvasId = props.canvasId) {
  if (!canvasId) return
  loadingSession.value = true
  generationDialogOpen.value = false
  pendingPlan.value = null
  try {
    const detail = await getSessionHistory(sessionId, canvasId)
    if (currentSessionId.value !== sessionId || props.canvasId !== canvasId) return
    messages.value = detail.conversations as ChatMessage[]
    activeTasks.value = detail.tasks || []
    if (detail.generation_request) openGenerationDialog(detail.generation_request)
  } catch { ElMessage.error('会话加载失败，请重试') }
  finally { loadingSession.value = false }
}

async function loadSessions(canvasId = props.canvasId) {
  if (!canvasId) {
    sessions.value = []
    return
  }
  historyError.value = ''
  try {
    const loaded = await getUserSessions(canvasId)
    if (props.canvasId === canvasId) sessions.value = loaded
  }
  catch (error) { historyError.value = error instanceof Error ? error.message : '历史窗口加载失败' }
}

async function selectSession(sessionId: string) {
  if (isProcessing.value || loadingSession.value) return
  createNewSession()
  currentSessionId.value = sessionId
  historyOpen.value = false
    await loadSessionDetail(sessionId, props.canvasId)
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
  optimizationTarget.value = undefined
  selectedSkillId.value = ''
}

async function startPromptOptimization(target: PromptOptimizationTarget, skillId: string) {
  if (!skillId) { ElMessage.warning('请先选择技能'); return false }
  if (isProcessing.value || loadingSession.value || props.homeLoading) { ElMessage.info('请等待当前对话完成后再优化'); return false }
  const model = composer.value?.selectedModel ?? availableModels.value[0]
  if (!model) { ElMessage.warning('暂无可用对话模型，请配置后重试'); return false }
  createNewSession()
  optimizationTarget.value = target
  selectedSkillId.value = skillId
  emit('update:modelValue', true)
  await nextTick()
  composer.value?.setPrompt('')
  return await handleSubmit({
    prompt: skillId === 'image-prompt-reverse'
      ? `请根据当前节点连接的上游参考图片反推提示词，只返回文字，不生成图片或视频。\n\n${target.prompt}`
      : `请优化以下${target.mediaType === 'video' ? '视频' : '图片'}提示词。需要补充关键信息时先向我提问。\n当前节点参数：${JSON.stringify(target.parameters)}\n\n${target.prompt}`,
    skillId, model, useWebSearch: false, attachedFile: null,
  })
}

function selectAssets(assets: Array<{ id: number; location: string; asset_type?: string }>) {
  for (const a of assets) {
    if (selectedAssets.value.length >= 10) break
    if (selectedAssets.value.some(s => s.id === a.id)) continue
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
  // 素材映射由服务端保留，编辑框只展示创作描述。
  const editablePrompt = (prompt: string) => prompt.split('\n\n本次上传的参考素材对应关系：\n')[0]!
  pendingPlan.value = request.media_type === 'plan' ? { ...request, steps: request.steps.map(step => ({ ...step, prompt: editablePrompt(step.prompt) })) } : null
  planOptions.value = {}
  pendingGenerationPrompt.value = editablePrompt(request.prompt)
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
const videoDurationField = computed(() => generationModels.value.find(model => model.id === generationModelId.value)?.parameters?.fields?.find(field => field.key === 'duration'))
const videoDurationMin = computed(() => videoDurationField.value?.min ?? 1)
const videoDurationMax = computed(() => videoDurationField.value?.max ?? 60)
const videoDurationStep = computed(() => videoDurationField.value?.step ?? 1)

watch([generationModelId, videoDurationField, fixedVideoDuration], () => {
  if (generationType.value !== 'video' || generationModelId.value == null || fixedVideoDuration.value) return
  const min = videoDurationMin.value
  const step = videoDurationStep.value
  const value = videoDuration.value ?? Number(videoDurationField.value?.default ?? min)
  videoDuration.value = Math.max(min, Math.min(videoDurationMax.value, min + Math.round((value - min) / step) * step))
})

watch([generationModelId, videoResolutionOptions], () => {
  if (generationType.value !== 'video') return
  const options = videoResolutionOptions.value
  if (!options.some(option => option.value === videoResolution.value)) {
    videoResolution.value = options[0]?.value ?? null
  }
})

function validVideoDuration(value: number) {
  return value >= videoDurationMin.value && value <= videoDurationMax.value
    && Math.abs((value - videoDurationMin.value) / videoDurationStep.value - Math.round((value - videoDurationMin.value) / videoDurationStep.value)) < 1e-8
}

async function confirmGeneration() {
  // 这里只确认用户可编辑的提示词和生成参数，计划依赖关系仍以后端返回的数据为准。
  if (isProcessing.value) return
  if (pendingPlan.value ? pendingPlan.value.steps.some(step => !step.prompt.trim()) : !pendingGenerationPrompt.value.trim()) {
    generationDialogError.value = '请填写提示词，任务中的每一步都不能为空。'
    return
  }
  const options = generationType.value === 'image'
    ? { media_type: 'image' as const, model: generationModelId.value, n: imageCount.value, aspect_ratio: imageAspectRatio.value, quality: imageQuality.value }
    : { media_type: 'video' as const, model: generationModelId.value, aspect_ratio: videoRatio.value, resolution: videoResolution.value, duration: videoDuration.value }
  if (Object.values(options).some(v => v === null || v === undefined || v === '')) {
    generationDialogError.value = '请先选择模型，并填写全部生成参数。'
    return
  }
  if (generationType.value === 'video') {
    const durations = pendingPlan.value?.steps.filter(step => step.media_type === 'video').map(step => step.duration ?? videoDuration.value!) ?? [videoDuration.value!]
    if (durations.some(value => !validVideoDuration(value))) {
      generationDialogError.value = `当前模型支持 ${videoDurationMin.value}–${videoDurationMax.value} 秒，步长 ${videoDurationStep.value} 秒，请调整时长或选择其他模型。`
      return
    }
  }
  const model = lastSubmitData?.model || availableModels.value[0]
  if (!model) { generationDialogError.value = '请先加载对话模型后重试。'; return }
  let confirmed: WorkflowMessageRequest['generation_options'] = { ...options, prompt: pendingGenerationPrompt.value.trim() }
  if (pendingPlan.value) {
    planOptions.value[options.media_type] = options
    const next = pendingPlan.value.steps.find(step => !planOptions.value[step.media_type])
    if (next) { resetGenerationFields(next.media_type); return }
    confirmed = { media_type: 'plan', plan_id: pendingPlan.value.plan_id, ...planOptions.value,
      step_prompts: Object.fromEntries(pendingPlan.value.steps.map(step => [step.id, step.prompt.trim()])) }
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
  if (!task.plan_id || !currentSessionId.value || !props.canvasId || retryingPlan.value) return
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

const handleSubmit = async (data: ChatSubmitData, confirmedOptions?: WorkflowMessageRequest['generation_options'], requestedName?: string) => {
  if (isProcessing.value || loadingSession.value || props.homeLoading) return
  if (optimizationTarget.value && !data.skillId) { ElMessage.warning('请先选择技能'); return false }
  if (props.homeMode && !props.canvasId && !requestedName) {
    canvasName.value = ''
    canvasDialogError.value = ''
    canvasDialog.value = { type: 'create', submission: data }
    composer.value?.setPrompt(data.prompt)
    return
  }
  lastSubmitData = data
  const submittedAssets = confirmedOptions ? [] : [...selectedAssets.value]
  const assetMentions: Record<number, string> = {}
  if (!confirmedOptions) {
    const referencedIds = new Set<number>()
    for (const match of data.prompt.matchAll(/@(图|图片|视频)(\d+)/g)) {
      const type = match[1] === '视频' ? 'video' : 'image'
      const item = referenceItems.value.filter(item => item.type === type)[Number(match[2]) - 1]
      if (!item?.url) { ElMessage.warning(`引用 ${match[0]} 已不可用，请重新选择素材`); return }
      referencedIds.add(item.id)
    }
    // 按界面编号收集，不能让提示词中先出现的“图片3”变成模型收到的第一张图。
    for (const item of referenceItems.value) {
      if (referencedIds.has(item.id) && !submittedAssets.some(asset => asset.id === item.id)) submittedAssets.push({ id: item.id, url: item.url, asset_type: item.type === 'video' ? 'video' : 'picture' })
      if (submittedAssets.some(asset => asset.id === item.id)) assetMentions[item.id] = item.mention
    }
    if (submittedAssets.length > 10) { ElMessage.warning('每条消息最多引用 10 个素材'); return }
  }

  messages.value.push({ role: 'user', message: data.prompt, assets: submittedAssets, created_at: new Date().toISOString() })
  const userMessage = messages.value[messages.value.length - 1]!
  messages.value.push({ role: 'agent', message: '', created_at: new Date().toISOString() })
  const agentMessage = messages.value[messages.value.length - 1]!

  isProcessing.value = true
  const controller = new AbortController()
  chatController = controller
  canStop.value = true
  emit('busy-change', true)
  await nextTick(scrollToBottom)

  let targetCanvasId: number | undefined
  try {
    targetCanvasId = (await props.prepareCanvas(requestedName)) ?? props.canvasId
    controller.signal.throwIfAborted()
    if (!targetCanvasId) throw new Error('画布创建失败，请重试')
    const response = await sendWorkflowMessageStream(
      { canvas_id: targetCanvasId, message: data.prompt, model_id: Number(data.model.id), session_id: currentSessionId.value, generation_options: confirmedOptions, asset_ids: submittedAssets.map(a => a.id), asset_mentions: assetMentions, skill_id: confirmedOptions ? undefined : data.skillId, prompt_optimization: !!optimizationTarget.value, optimization_node_id: optimizationTarget.value?.nodeId },
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
      controller.signal,
    )
    canStop.value = false
    agentMessage.context_usage = response.context_usage ?? agentMessage.context_usage
    agentMessage.optimizedPrompt = response.optimized_prompt || undefined
    if (!confirmedOptions && !optimizationTarget.value) selectedSkillId.value = ''
    activeTasks.value = response.tasks || []
    if (!confirmedOptions) selectedAssets.value = []
    userMessage.id = response.user_conversation_id ?? undefined
    agentMessage.id = response.agent_conversation_id ?? undefined
    // 只有 generation_request 才表示“提示词已就绪，等待参数确认”。
    // 追问/校验失败时后端只保存草稿并回复问题，必须清掉旧面板，避免继续确认过期计划。
    if (response.generation_request) openGenerationDialog(response.generation_request)
    else if (!confirmedOptions || response.workflow_ready) {
      pendingPlan.value = null
      generationDialogOpen.value = false
      generationType.value = 'none'
    }

    const sessionChanged = Boolean(response.session_id && response.session_id !== currentSessionId.value)
    if (sessionChanged) currentSessionId.value = response.session_id

    agentMessage.message = response.reply

    await loadSessions(targetCanvasId)
    return true
  } catch (error) {
    if (controller.signal.aborted) {
      agentMessage.stopped = true
      return false
    }
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'agent') {
      last.failed = true
      last.message = error instanceof Error ? error.message : '抱歉，处理您的请求时出现错误。'
    }
    if (props.homeMode) composer.value?.setPrompt(data.prompt)
    return false
  } finally {
    chatController = undefined
    canStop.value = false
    isProcessing.value = false
    emit('busy-change', false)
    if (targetCanvasId) emit('canvas-changed', targetCanvasId)
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
    if (!props.canvasId) return
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
  void loadSkills()
  loadingSession.value = true
  await loadSessions()
  if (sessions.value.length > 0) {
    currentSessionId.value = sessions.value[0]!.id
    await loadSessionDetail(sessions.value[0]!.id)
  }
  loadingSession.value = false
  taskPoller = setInterval(() => { void pollTasksOnce() }, 3000)
})

watch(() => [props.canvasId, props.homeMode] as const, async ([canvasId, homeMode], [, previousHomeMode]) => {
  if (isProcessing.value) return
  if (homeMode && previousHomeMode) return
  loadingSession.value = false
  createNewSession()
  if (!canvasId || homeMode) return
  loadingSession.value = true
  await loadSessions(canvasId)
  if (props.canvasId !== canvasId) return
  if (sessions.value.length > 0) {
    currentSessionId.value = sessions.value[0]!.id
    await loadSessionDetail(sessions.value[0]!.id, canvasId)
  }
  loadingSession.value = false
})


onUnmounted(() => { stopProcessing(); if (taskPoller) clearInterval(taskPoller) })
defineExpose({ startPromptOptimization, openCreateCanvasDialog })
</script>

<template>
  <aside class="ai-panel" :class="{ open: modelValue || homeMode, 'home-mode': homeMode }" aria-label="若晴AI面板">
    <header v-if="!homeMode" class="ai-panel-header">
      <div class="ai-panel-title">
        <AiBlobWarpAvatar class="panel-avatar" />
        <span>若晴AI</span>
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

    <section v-if="homeMode" class="canvas-home-intro" aria-labelledby="canvas-home-title">
      <p class="canvas-home-kicker">若晴 · AI 画布</p>
      <h1 id="canvas-home-title">今天要做点什么？</h1>
      <p>把一句想法交给 AI，它会在画布里整理节点、生成素材并保留完整过程。</p>
    </section>

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
              :stopped="item.message.stopped"
            />
            <p v-if="item.message.message" :class="{ 'msg-error': item.message.failed }">
              {{ item.message.message }}
            </p>
            <p v-if="item.message.stopped" class="msg-stopped" role="status">已停止</p>
            <p v-if="item.message.optimizedPrompt && !item.message.message.includes(item.message.optimizedPrompt)">{{ item.message.optimizedPrompt }}</p>
            <div v-if="optimizationTarget && item.message.optimizedPrompt" class="ai-elements prompt-result-actions">
              <Button type="button" variant="outline" size="sm" :disabled="isProcessing" @click="emit('apply-prompt', optimizationTarget, item.message.optimizedPrompt)">应用到提示词</Button>
            </div>
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
          <p v-if="item.task.warning" class="task-error task-warning" role="status">{{ item.task.warning }}</p>
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
      <div v-if="optimizationTarget" class="optimization-context">
        <span>正在优化：{{ optimizationTarget.label }}<small>补充细节后，将结果应用到原节点</small></span>
        <Button type="button" variant="ghost" size="icon-xs" :disabled="isProcessing" aria-label="结束提示词优化" title="结束提示词优化" @click="createNewSession"><X :size="14" /></Button>
      </div>
      <Button v-if="pendingPlan && !generationDialogOpen" variant="outline" :disabled="isProcessing || loadingSession" @click="openGenerationDialog(pendingPlan)">继续确认任务计划</Button>
      <div v-if="selectedAssets.length" class="panel-attachments">
        <div v-for="asset in selectedAssets" :key="asset.id" class="panel-asset">
          <video v-if="asset.asset_type === 'video'" :src="asset.url" muted preload="metadata" />
          <img v-else :src="asset.url" alt="" />
          <button class="asset-remove" :disabled="isProcessing" @click="selectedAssets = selectedAssets.filter(a => a.id !== asset.id)">×</button>
        </div>
      </div>
      <AiChatComposer
        ref="composer"
        :key="homeMode ? 'home' : canvasId"
        :models="availableModels"
        :on-submit="handleSubmit"
        :is-processing="isProcessing || loadingSession || homeLoading"
        :can-stop="canStop"
        :asset-count="selectedAssets.length"
        :skill-id="selectedSkillId"
        :requires-skill="!!optimizationTarget"
        :context-usage="contextUsage"
        :references="referenceItems"
        @assets="assetPickerOpen = true"
        @stop="stopProcessing"
      >
        <template #skills>
          <ChatSkillPicker v-model="selectedSkillId" :skills="skills" :loading="skillsLoading" :error="skillsError" :disabled="isProcessing || loadingSession || homeLoading" @refresh="loadSkills" />
        </template>
        <template v-if="homeMode" #workspace>
          <Select :model-value="canvasId ? String(canvasId) : 'new'" :disabled="isProcessing || loadingSession || homeLoading" @update:model-value="emit('select-canvas', $event === 'new' ? undefined : Number($event))">
            <SelectTrigger class="workspace-select" aria-label="选择画布"><Folder :size="14" /><SelectValue placeholder="选择画布" /></SelectTrigger>
            <SelectContent class="ai-elements">
              <SelectItem value="new">新画布 · 提交时创建</SelectItem>
              <SelectItem v-for="board in boards ?? []" :key="board.id" :value="String(board.id)">{{ board.name }}</SelectItem>
            </SelectContent>
          </Select>
        </template>
      </AiChatComposer>
      <p v-if="homeMode && messages.at(-1)?.failed" role="alert" class="task-error">{{ messages.at(-1)?.message }}</p>
      <p v-if="homeMode && messages.at(-1)?.stopped" role="status" class="msg-stopped">已停止</p>
      <div v-if="homeMode" class="canvas-library" aria-label="已有画布">
        <div class="canvas-library-head">
          <span>我的画布</span>
          <span class="canvas-library-count">{{ boards?.length ?? 0 }} 个</span>
        </div>
        <p v-if="homeError" role="alert" class="task-error">{{ homeError }}</p>
        <p v-else-if="homeLoading" class="canvas-library-empty">正在加载画布…</p>
        <div class="canvas-library-grid">
          <button type="button" class="canvas-library-card canvas-library-create" :disabled="isProcessing || loadingSession || homeLoading" @click="emit('create-canvas')">
            <span class="canvas-library-icon"><PlusIcon :size="16" /></span>
            <span class="canvas-library-name">新建画布</span>
            <span class="canvas-library-date">创建空白画布</span>
          </button>
          <div v-for="board in boards" :key="board.id" class="canvas-library-card">
            <button type="button" class="canvas-library-main" :disabled="isProcessing || loadingSession || homeLoading" @click="emit('open-canvas', board.id)">
              <span class="canvas-library-icon">✦</span>
              <span class="canvas-library-name">{{ board.name }}</span>
              <span class="canvas-library-date">{{ formatTime(new Date(board.updated_at).toISOString()) }}更新</span>
            </button>
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <button type="button" class="canvas-library-menu" :disabled="isProcessing || loadingSession || homeLoading" :aria-label="`${board.name}的画布操作`" title="画布操作" @click.stop><MoreVertical :size="16" /></button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" class="ai-elements canvas-menu-content">
                <DropdownMenuItem @select="emit('open-canvas', board.id)"><ExternalLink :size="14" />打开</DropdownMenuItem>
                <DropdownMenuItem @select="openCanvasDialog('rename', board)"><Pencil :size="14" />重命名</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" @select="openCanvasDialog('delete', board)"><Trash2 :size="14" />删除</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>
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
                <Textarea v-model="step.prompt" :aria-label="`${step.label}提示词`" class="generation-prompt-editor" :disabled="isProcessing" />
                <small v-if="step.depends_on.length">等待：{{ step.depends_on.map(id => pendingPlan?.steps.find(item => item.id === id)?.label).join('、') }}</small>
              </li>
            </ol>
            <label v-else class="gen-field generation-prompt">生成提示词<Textarea v-model="pendingGenerationPrompt" aria-label="生成提示词" class="generation-prompt-editor" :disabled="isProcessing" /></label>
            <div class="generation-fields">
              <div class="gen-field">
                <span>生成模型</span>
                <Select :model-value="generationModelId == null ? undefined : String(generationModelId)" @update:model-value="generationModelId = $event ? Number($event) : null">
                  <SelectTrigger class="w-full"><SelectValue placeholder="选择生成模型" /></SelectTrigger>
                  <SelectContent class="ai-elements">
                    <SelectItem v-for="m in generationModels" :key="m.id" :value="String(m.id)">{{ m.description || m.name }}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <template v-if="generationType === 'image'">
                <div class="gen-field"><span>画面比例</span><SegmentedControl :model-value="imageAspectRatio || ''" :options="imageRatios" :show-ratio-shapes="true" label="图片比例" @update:model-value="imageAspectRatio = $event" /></div>
                <div class="gen-field"><span>图片质量</span><SegmentedControl :model-value="imageQuality || ''" :options="[{value:'low',label:'低'},{value:'medium',label:'中'},{value:'high',label:'高'}]" label="图片质量" @update:model-value="imageQuality = $event" /></div>
                <label>{{ pendingPlan ? '每步生成张数' : '生成张数' }}<ElInputNumber v-model="imageCount" :min="1" :max="10" :disabled="!!pendingPlan" /></label>
              </template>
              <template v-else>
                <div class="gen-field"><span>画面比例</span><SegmentedControl :model-value="videoRatio || ''" :options="videoRatios" :show-ratio-shapes="true" label="视频比例" @update:model-value="videoRatio = $event" /></div>
                <div class="gen-field"><span>分辨率</span><SegmentedControl :model-value="videoResolution || ''" :options="videoResolutionOptions" label="分辨率" @update:model-value="videoResolution = $event" /></div>
                <label class="gen-field"><span>视频时长 <span class="duration-value">{{ videoDuration ?? '—' }} 秒</span></span><ElSlider :model-value="videoDuration ?? videoDurationMin" :min="videoDurationMin" :max="videoDurationMax" :step="videoDurationStep" :disabled="generationModelId == null || fixedVideoDuration" :show-tooltip="false" aria-label="视频时长" @update:model-value="videoDuration = Number($event)" /></label>
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

    <Dialog v-model:open="canvasDialogOpen">
      <DialogContent class="ai-elements canvas-dialog">
        <DialogHeader>
          <DialogTitle>{{ canvasDialog?.type === 'create' ? '新建画布' : canvasDialog?.type === 'rename' ? '重命名画布' : '删除画布' }}</DialogTitle>
          <DialogDescription v-if="canvasDialog?.type === 'delete'">确认删除「{{ canvasDialog.board.name }}」？画布会从首页移除，已生成的素材仍会保留。</DialogDescription>
          <DialogDescription v-else>给这个画布取一个容易识别的名称。</DialogDescription>
        </DialogHeader>
        <Input v-if="canvasDialog?.type !== 'delete'" v-model="canvasName" :disabled="canvasDialogBusy" :maxlength="100" aria-label="画布名称" autofocus placeholder="例如：品牌海报方案" @keyup.enter="confirmCanvasDialog" />
        <p v-if="canvasDialogError" role="alert" class="task-error">{{ canvasDialogError }}</p>
        <DialogFooter>
          <Button variant="outline" :disabled="canvasDialogBusy" @click="canvasDialog = undefined">取消</Button>
          <Button :variant="canvasDialog?.type === 'delete' ? 'destructive' : 'default'" :disabled="canvasDialogBusy" @click="confirmCanvasDialog">
            {{ canvasDialogBusy ? '处理中…' : canvasDialog?.type === 'delete' ? '确认删除' : canvasDialog?.type === 'create' ? (canvasDialog.submission ? '创建并发送' : '创建') : '保存' }}
          </Button>
        </DialogFooter>
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
.ai-panel.home-mode {
  position: relative;
  right: auto;
  bottom: auto;
  width: min(900px, 100%);
  height: auto;
  min-height: 0;
  margin: 0 auto;
  border: 0;
  border-radius: 0;
  background: transparent;
  backdrop-filter: none;
  box-shadow: none;
  transform: none;
}
.canvas-home-intro { padding: 0 0 28px; }
.canvas-home-kicker { color: var(--color-muted); font-size: 10px; letter-spacing: .18em; }
.canvas-home-intro h1 { margin-top: 12px; font-size: clamp(26px, 4vw, 36px); line-height: 1.2; letter-spacing: -.02em; }
.canvas-home-intro p:last-child { max-width: 520px; margin-top: 14px; color: var(--color-muted); font-size: 14px; line-height: 1.7; }
.home-mode .ai-panel-messages { display: none; }
.home-mode .ai-panel-input { border-top: 0; padding: 0; background: transparent; }
.home-mode .ai-panel-input :deep([data-slot="input-group"]) { border: 1px solid var(--color-border); border-radius: 22px; background: var(--color-surface); }
.home-mode .ai-panel-input :deep(textarea) { min-height: 138px; padding: 22px; border: 0; border-radius: 22px 22px 0 0; background: transparent; box-shadow: none; resize: none; font-size: 15px; }
.home-mode .ai-panel-input :deep(.el-textarea__inner) { border: 0 !important; background: transparent !important; box-shadow: none !important; }
.home-mode .ai-panel-input :deep(.mention-textarea) { background: transparent; }
.home-mode .ai-panel-input :deep(.mention-highlight) { padding: 22px; font-size: 15px; line-height: 1.5; }
.home-mode .ai-panel-input :deep(.composer-workspace-row) { padding: 0 14px 4px; }
.workspace-select { max-width: min(300px, 65vw); min-width: 0; border: 0; border-radius: 8px; padding: 5px 8px; background: transparent; color: var(--color-muted); font-size: 12px; cursor: pointer; }
.workspace-select:hover, .workspace-select:focus { background: var(--color-surface-soft); color: var(--color-text); }
.workspace-select:disabled { cursor: default; opacity: .6; }
.canvas-library { margin-top: 44px; }
.canvas-library-head { display: flex; align-items: center; gap: 8px; margin: 10px 0 12px; color: var(--color-text); font-size: 14px; font-weight: 600; }
.canvas-library-count { color: var(--color-muted); font-size: 11px; font-weight: 400; }
.canvas-library-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
.canvas-library-card { position: relative; min-width: 0; display: flex; flex-direction: column; align-items: flex-start; gap: 7px; padding: 14px; border: 1px solid var(--color-border); border-radius: 14px; background: rgba(var(--color-white-rgb), .035); color: var(--color-text); text-align: left; transition: border-color .2s, background .2s, transform .2s; }
.canvas-library-card:hover, .canvas-library-card:focus-visible { border-color: var(--color-border-strong); background: var(--color-surface-soft); transform: translateY(-2px); }
.canvas-library-create { font: inherit; cursor: pointer; }
.canvas-library-create:disabled { opacity: .5; cursor: not-allowed; transform: none; }
.canvas-library-main { display: flex; min-width: 0; width: 100%; flex-direction: column; align-items: flex-start; gap: 7px; border: 0; padding: 0; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.canvas-library-menu { position: absolute; top: 8px; right: 8px; display: grid; width: 28px; height: 28px; place-items: center; border: 0; border-radius: 8px; background: transparent; color: var(--color-muted); cursor: pointer; transition: background .2s, color .2s; }
.canvas-library-menu:hover { background: var(--color-surface-soft); color: var(--color-text); }
.canvas-library-icon { display: grid; width: 27px; height: 27px; place-items: center; border-radius: 8px; background: rgba(var(--color-white-rgb), .08); color: var(--color-muted); font-size: 13px; }
.canvas-library-name { width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.canvas-library-date, .canvas-library-empty { color: var(--color-muted); font-size: 11px; }
.canvas-library-empty { padding: 12px 0 4px; }
.canvas-menu-content { min-width: 132px; }
.canvas-menu-content [data-slot="dropdown-menu-item"] { gap: 8px; }
.canvas-dialog { max-width: 420px; }
.canvas-dialog :deep(input) { min-height: 40px; color: var(--color-text); }

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
.msg-stopped { color: var(--color-muted); font-size: 12px; }
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
.task-warning { color: var(--color-warning); }
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
.generation-prompt-editor { min-height: 100px; max-height: 240px; overflow-y: auto; resize: vertical; font-size: 13px; line-height: 1.6; }
.optimization-context { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; color: var(--color-text); font-size: 12px; }
.optimization-context span { min-width: 0; overflow-wrap: anywhere; }
.optimization-context small { display: block; margin-top: 4px; color: var(--color-muted); }
.prompt-result-actions { margin-top: 10px; }
.generation-prompt { font-size: 13px; line-height: 1.6; margin-bottom: 14px; color: var(--color-text); }
.generation-fields { display: flex; flex-direction: column; gap: 12px; }
.gen-field { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--color-muted); }
.duration-value { float: right; color: var(--color-text); font-variant-numeric: tabular-nums; }

@media (max-width: 600px) {
  .ai-panel { width: 100vw; height: min(660px, calc(100dvh - 56px)); border-radius: 18px 0 0 0; }
  .ai-panel.home-mode { width: 100%; height: auto; border-radius: 0; }
  .ai-panel-input { padding-bottom: max(12px, env(safe-area-inset-bottom)); }
}
@media (prefers-reduced-motion: reduce) {
  .ai-panel { transition: none; }
  .ai-panel-messages { scroll-behavior: auto; }
  .canvas-library-card { transition: none; }
  .canvas-library-card:hover { transform: none; }
  .task-spinner { animation: none; }
}
</style>
