<template>
  <div class="chat-page ai-elements">
    <aside class="sessions-sidebar">
      <div class="sidebar-header"><span class="section-label">创作对话</span><Button variant="outline" size="sm" :disabled="isProcessing" @click="createNewSession"><PlusIcon class="size-4" />新会话</Button></div>
      <nav class="sessions-list" aria-label="历史会话">
        <div v-for="session in sessions" :key="session.id" :class="['session-item', { active: session.id === currentSessionId }]">
          <button class="session-select" :disabled="isProcessing" :aria-current="session.id === currentSessionId ? 'page' : undefined" @click="switchSession(session.id)">
          <MessageSquareIcon class="size-4 shrink-0" /><span class="session-info"><span class="session-title">{{ session.intent || '新会话' }}</span><span class="session-meta">{{ getStatusText(session.status) }} · {{ formatTime(session.updated_at) }}</span></span>
          </button>
          <button class="session-delete" type="button" :disabled="isProcessing" :aria-label="`删除会话 ${session.intent || '新会话'}`" title="删除会话" @click="deleteSessionFromList(session.id)"><Trash2Icon class="size-4" /></button>
        </div>
        <p v-if="!sessions.length" class="empty-sessions">还没有历史会话</p>
      </nav>
    </aside>
    <main class="chat-content">
      <header class="chat-header">
        <div class="flex items-center gap-2"><AiBlobWarpAvatar /><strong>AI 创作助手</strong></div>
        <Context v-model:open="contextOpen" :used-tokens="contextUsage?.used_tokens ?? 0" :max-tokens="contextUsage?.max_tokens ?? 0">
          <ContextTrigger><Button variant="ghost" size="sm" @click="contextOpen = true"><ContextIcon />上下文<span class="text-muted-foreground">{{ contextPercent }}</span></Button></ContextTrigger>
          <ContextContent class="ai-elements context-panel" align="end">
            <ContextContentHeader v-if="contextUsage?.used_tokens != null && contextUsage.max_tokens" />
            <ContextContentBody class="space-y-3">
              <strong>当前上下文</strong><p>{{ messages.length }} 条消息 · {{ contextAssetCount }} 个参考资产</p>
              <template v-if="contextUsage">
                <p class="text-xs text-muted-foreground">{{ contextUsage.model }} · 最近一轮模型请求</p>
                <dl class="context-usage"><dt>窗口占用</dt><dd>{{ formatTokens(contextUsage.used_tokens) }} / {{ formatTokens(contextUsage.max_tokens, '上限未知') }}</dd><dt>输入令牌</dt><dd>{{ formatTokens(contextUsage.input_tokens) }}</dd><dt>输出令牌</dt><dd>{{ formatTokens(contextUsage.output_tokens) }}</dd><template v-if="contextUsage.reasoning_tokens != null"><dt>其中推理令牌</dt><dd>{{ formatTokens(contextUsage.reasoning_tokens) }}</dd></template><template v-if="contextUsage.cached_tokens != null"><dt>其中缓存输入</dt><dd>{{ formatTokens(contextUsage.cached_tokens) }}</dd></template></dl>
                <p class="text-xs text-muted-foreground">用量以模型接口返回为准，包含系统规则、历史消息、参考资产与工具信息；各轮请求不累加。{{ contextUsage.used_tokens == null ? '当前接口未返回令牌用量。' : '' }}</p>
              </template>
              <p v-else class="text-xs text-muted-foreground">发送消息后显示模型接口返回的令牌用量。</p>
              <div v-if="messages.some(message => message.role === 'agent' && message.id)" class="space-y-1"><p class="text-xs text-muted-foreground">已保存的检查点</p><Button v-for="message in messages.filter(entry => entry.role === 'agent' && entry.id)" :key="message.id" class="w-full justify-start" size="sm" variant="ghost" @click="locateCheckpoint(message.id!); contextOpen = false">定位回复 #{{ message.id }}</Button></div>
            </ContextContentBody>
          </ContextContent>
        </Context>
      </header>
      <div v-if="isLoadingModels" class="welcome-container"><p>正在加载模型…</p></div>
      <template v-else>
        <div v-if="!messages.length" class="welcome-container">
          <AiBlobWarpAvatar class="welcome-icon" /><h1>从一个想法开始</h1><p>一起打磨提示词，让图片与视频逐步成形。</p>
          <div class="welcome-suggestions"><Suggestion v-for="text in suggestions" :key="text" :suggestion="text" @click="composer?.setPrompt" /></div>
        </div>
        <Conversation v-else :key="currentSessionId || 'new'" class="chat-conversation" aria-label="创作对话消息">
          <ConversationContent class="conversation-inner">
            <template v-for="item in conversationItems" :key="item.key">
              <div v-if="item.type === 'message'" :id="item.message.id ? `conversation-${item.message.id}` : undefined" :class="['message-row', { 'checkpoint-selected': selectedCheckpoint === item.message.id && item.message.id != null }]">
                <Message :from="item.message.role === 'user' ? 'user' : 'assistant'" class="chat-message flex-col items-start">
                  <div class="message-author">{{ item.message.role === 'user' ? '你' : '创作助手' }}<span>{{ formatTime(item.message.created_at) }}</span></div>
                  <ChainOfThought v-if="item.message.events?.length || item.message.steps?.length" :default-open="isProcessing && item.index === messages.length - 1" class="execution-trace">
                    <ChainOfThoughtHeader>执行过程{{ isProcessing && item.index === messages.length - 1 ? ' · 处理中' : item.message.failed ? ' · 已中断' : ' · 已结束' }}</ChainOfThoughtHeader>
                    <ChainOfThoughtContent>
                      <template v-if="item.message.events?.length">
                        <template v-for="(event, index) in item.message.events" :key="index">
                          <ChainOfThoughtStep v-if="event.type === 'model_request'" :label="`第 ${event.round + 1} 轮 · ${event.model}`" :description="`使用 ${event.message_count} 条上下文消息，可用工具：${event.tools.join('、')}`"><template #icon><CheckIcon class="size-3" /></template></ChainOfThoughtStep>
                          <Tool v-else-if="event.type === 'tool_call'" :default-open="event.name === 'discover_tools'" class="trace-tool">
                            <ToolHeader type="dynamic-tool" :tool-name="event.name" :state="traceToolState(item.message, event.call_id)" />
                            <ToolContent><ToolInput :input="event.input" /><ToolOutput v-if="traceResult(item.message, event.call_id)" :output="traceResult(item.message, event.call_id)" :error-text="traceError(item.message, event.call_id)" /></ToolContent>
                          </Tool>
                        </template>
                      </template>
                      <template v-else><ChainOfThoughtStep v-for="(step, index) in item.message.steps" :key="index" :label="step" :status="isProcessing && item.index === messages.length - 1 && index === item.message.steps!.length - 1 ? 'active' : 'complete'"><template #icon><CheckIcon class="size-3" /></template></ChainOfThoughtStep></template>
                      <p v-if="isProcessing && item.index === messages.length - 1 && item.message.steps?.length" class="text-xs text-muted-foreground" role="status">{{ item.message.steps.at(-1) }}</p>
                    </ChainOfThoughtContent>
                  </ChainOfThought>
                  <MessageContent :class="{ 'task-error': item.message.failed }">
                    <MessageResponse v-if="item.message.role === 'agent' && item.message.message" :content="item.message.message" />
                    <p v-else-if="item.message.message" class="user-text">{{ item.message.message }}</p>
                    <p v-else-if="isProcessing" class="text-muted-foreground animate-pulse">正在处理…</p>
                    <div v-if="item.message.assets?.length" class="task-images"><template v-for="asset in item.message.assets" :key="asset.id"><video v-if="asset.asset_type === 'video'" :src="asset.url" controls preload="metadata" /><img v-else :src="asset.url" :alt="`参考图片 ${asset.id}`" loading="lazy" /></template></div>
                  </MessageContent>
                  <MessageActions v-if="item.message.role === 'agent' && item.message.message"><MessageAction label="复制回复" title="复制回复" @click="copyMessage(item.message.message)"><CopyIcon class="size-3.5" /></MessageAction></MessageActions>
                </Message>
                <Checkpoint v-if="item.message.role === 'agent' && item.message.id" class="saved-checkpoint"><CheckpointIcon /><CheckpointTrigger @click="locateCheckpoint(item.message.id!)">检查点 · 回复 #{{ item.message.id }} 已保存</CheckpointTrigger></Checkpoint>
              </div>
              <Tool v-else :default-open="true" class="generation-tool">
                <ToolHeader type="dynamic-tool" :tool-name="item.task.media_type === 'video' ? '视频生成' : '图片生成'" :title="item.task.model_name || (item.task.media_type === 'video' ? '视频生成' : '图片生成')" :state="taskState(item.task)" />
                <ToolContent><div class="tool-details"><p>{{ item.task.parameters?.prompt }}</p><dl class="task-parameters"><template v-for="(value, key) in item.task.parameters" :key="key"><template v-if="key !== 'prompt' && value != null"><dt>{{ parameterLabels[key] || key }}</dt><dd>{{ key === 'quality' ? (qualityLabels[String(value)] || value) : value }}</dd></template></template></dl><p class="task-meta">任务 {{ item.task.task_id }}<span v-if="item.task.stage"> · {{ item.task.stage }}</span></p><p v-if="item.task.status === 'failed'" class="task-error">{{ item.task.error || '生成失败，请调整后重试。' }}</p><div v-if="item.task.images?.length" class="task-images"><a v-for="image in item.task.images" :key="image.asset_id" :href="image.url" target="_blank" rel="noreferrer"><img :src="image.url" :alt="item.task.parameters?.prompt || '生成图片'" loading="lazy" /></a></div><div v-if="item.task.videos?.length" class="task-images"><video v-for="video in item.task.videos" :key="video.asset_id" :src="video.url" controls /></div></div></ToolContent>
              </Tool>
            </template>
          </ConversationContent>
          <ConversationScrollButton aria-label="回到最新消息" />
        </Conversation>
        <div class="input-container">
          <div v-if="generationType !== 'none' && pendingGenerationPrompt" class="pending-generation"><span>生成参数待确认</span><Button size="sm" variant="outline" :disabled="isProcessing" @click="generationDialogOpen = true">检查参数</Button></div>
          <AiChatComposer ref="composer" :models="availableModels" :on-submit="handleSubmit" :is-processing="isProcessing" :asset-count="selectedAssets.length" @assets="assetPickerOpen = true">
            <template #attachments><div v-if="selectedAssets.length" class="chat-assets"><div v-for="asset in selectedAssets" :key="asset.id" class="chat-asset"><video v-if="asset.asset_type === 'video'" :src="asset.url" muted preload="metadata" /><img v-else :src="asset.url" :alt="`参考图片 ${asset.id}`" /><Button variant="ghost" size="sm" :disabled="isProcessing" :aria-label="`移除参考资产 ${asset.id}`" @click="removeAsset(asset.id)">移除</Button></div></div></template>
          </AiChatComposer>
        </div>
      </template>
    </main>
    <Dialog v-model:open="generationDialogOpen">
      <DialogContent class="ai-elements generation-dialog" @interact-outside.prevent>
        <DialogHeader><DialogTitle>{{ generationType === 'video' ? '确认视频生成' : '确认图片生成' }}</DialogTitle><DialogDescription>检查提示词和参数，确认后开始生成。</DialogDescription></DialogHeader>
        <Confirmation :approval="{ id: currentSessionId || 'generation' }" state="approval-requested" class="border-0 p-0">
          <ConfirmationRequest>
            <p class="generation-dialog-prompt">{{ pendingGenerationPrompt }}</p>
            <div class="generation-dialog-fields">
              <div class="generation-choice"><span>生成模型</span><Select :model-value="generationModelId == null ? undefined : String(generationModelId)" @update:model-value="generationModelId = $event ? Number($event) : null"><SelectTrigger class="w-full" aria-label="生成模型"><SelectValue placeholder="选择生成模型" /></SelectTrigger><SelectContent class="ai-elements"><SelectItem v-for="model in generationModels" :key="model.id" :value="String(model.id)">{{ model.name }} · {{ model.provider }}</SelectItem></SelectContent></Select></div>
              <template v-if="generationType === 'image'">
                <div class="generation-choice"><span>画面比例</span><SegmentedControl :model-value="imageAspectRatio || ''" :options="imageRatios" label="图片比例" @update:model-value="imageAspectRatio = $event" /></div>
                <div class="generation-choice"><span>图片质量</span><SegmentedControl :model-value="imageQuality || ''" :options="[{value:'low',label:'低'},{value:'medium',label:'中'},{value:'high',label:'高'}]" label="图片质量" @update:model-value="imageQuality = $event" /></div>
                <label>生成张数<el-input-number v-model="imageCount" :min="1" :max="10" placeholder="张数" aria-label="生成张数" /></label>
              </template>
              <template v-else>
                <div class="generation-choice"><span>画面比例</span><SegmentedControl :model-value="videoRatio || ''" :options="videoRatios" label="视频比例" @update:model-value="videoRatio = $event" /></div>
                <div class="generation-choice"><span>分辨率</span><SegmentedControl :model-value="videoResolution || ''" :options="[{value:'720p',label:'720p'},{value:'1080p',label:'1080p'}]" label="视频分辨率" @update:model-value="videoResolution = $event" /></div>
                <label>视频时长（秒）<el-input-number v-model="videoDuration" :min="1" :max="60" placeholder="秒数" aria-label="视频时长" /></label>
              </template>
            </div>
            <p v-if="generationDialogError" role="alert" class="task-error">{{ generationDialogError }}</p>
          </ConfirmationRequest>
          <ConfirmationActions><ConfirmationAction variant="outline" @click="generationDialogOpen = false">稍后确认</ConfirmationAction><ConfirmationAction :disabled="isProcessing" @click="confirmGeneration">确认并生成</ConfirmationAction></ConfirmationActions>
        </Confirmation>
      </DialogContent>
    </Dialog>
    <AssetPicker v-model:visible="assetPickerOpen" :max-select="10 - selectedAssets.length" :allow-video="true" @select="selectAssets" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import AiChatComposer from '@/components/AiChatComposer.vue'
import AiBlobWarpAvatar from '@/components/AiBlobWarpAvatar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import { PlusIcon, CopyIcon, CheckIcon, MessageSquareIcon, Trash2Icon } from '@lucide/vue'
import { ElMessage } from 'element-plus'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Conversation, ConversationContent, ConversationScrollButton } from '@/components/ai-elements/conversation'
import { Message, MessageContent, MessageResponse, MessageActions, MessageAction } from '@/components/ai-elements/message'
import { ChainOfThought, ChainOfThoughtHeader, ChainOfThoughtContent, ChainOfThoughtStep } from '@/components/ai-elements/chain-of-thought'
import { Checkpoint, CheckpointIcon, CheckpointTrigger } from '@/components/ai-elements/checkpoint'
import { Context, ContextTrigger, ContextContent, ContextIcon, ContextContentHeader, ContextContentBody } from '@/components/ai-elements/context'
import { Tool, ToolHeader, ToolContent, ToolInput, ToolOutput } from '@/components/ai-elements/tool'
import { Confirmation, ConfirmationRequest, ConfirmationActions, ConfirmationAction } from '@/components/ai-elements/confirmation'
import { Suggestion } from '@/components/ai-elements/suggestion'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import AssetPicker from '@/components/AssetPicker.vue'
import type { ChatSubmitData, AIModel } from '@/types/ai-models'
import {
  sendWorkflowMessageStream,
  getLanguageModels,
  getUserSessions,
  deleteSession,
  getSessionHistory,
  getTaskStatus,
  type WorkflowMessageRequest,
  type WorkflowMessageResponse,
  type WorkflowSession,
  type WorkflowTask,
  type ConversationMessage,
  type ChatAsset,
} from '@/api/workflow'

const isProcessing = ref(false)
type ChatMessage = ConversationMessage & { steps?: string[]; failed?: boolean }
const composer = ref<InstanceType<typeof AiChatComposer>>()
const selectedCheckpoint = ref<number>()
const contextOpen = ref(false)
const contextUsage = computed(() => messages.value.findLast(message => message.context_usage != null)?.context_usage)
const contextPercent = computed(() => {
  const usage = contextUsage.value
  if (usage?.used_tokens == null) return '待统计'
  if (!usage.max_tokens) return '上限未知'
  return `${(usage.used_tokens / usage.max_tokens * 100).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}%`
})
function formatTokens(value: number | null | undefined, fallback = '未提供') {
  return value == null ? fallback : value.toLocaleString('zh-CN')
}
function traceResult(message: ChatMessage, callId: string) {
  const event = message.events?.find(event => event.type === 'tool_result' && event.call_id === callId)
  return event?.type === 'tool_result' ? event.output : undefined
}
function traceError(message: ChatMessage, callId: string) {
  const error = traceResult(message, callId)?.error
  return error ? String(error) : undefined
}
function traceToolState(message: ChatMessage, callId: string) {
  if (traceError(message, callId)) return 'output-error' as const
  if (traceResult(message, callId)) return 'output-available' as const
  return message.failed ? 'output-error' as const : 'input-available' as const
}
const contextAssetCount = computed(() => new Set([...messages.value.flatMap(message => message.assets?.map(asset => asset.id) || []), ...selectedAssets.value.map(asset => asset.id)]).size)
const suggestions = ['帮我完善图片提示词', '根据参考图片创作新画面', '帮我构思一段视频']
async function copyMessage(text: string) {
  try { await navigator.clipboard.writeText(text); ElMessage.success('已复制回复') }
  catch { ElMessage.error('复制失败，请手动选择文字复制') }
}
function locateCheckpoint(id: number) {
  selectedCheckpoint.value = id
  document.getElementById(`conversation-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
function taskState(task: WorkflowTask) {
  if (task.status === 'completed') return 'output-available' as const
  if (task.status === 'failed') return 'output-error' as const
  return 'input-available' as const
}
const messages = ref<ChatMessage[]>([])
const availableModels = ref<AIModel[]>([])
const isLoadingModels = ref(true)
const currentSessionId = ref<string | undefined>(undefined)
const sessions = ref<WorkflowSession[]>([])
const activeTasks = ref<WorkflowTask[]>([])
const assetPickerOpen = ref(false)
const selectedAssets = ref<ChatAsset[]>([])

function selectAssets(assets: Array<{ id: number; location: string; asset_type?: string }>) {
  for (const asset of assets) {
    if (selectedAssets.value.some((selected) => selected.id === asset.id)) continue
    if (selectedAssets.value.length >= 10) break
    selectedAssets.value.push({
      id: asset.id,
      asset_type: asset.asset_type === 'video' ? 'video' : 'picture',
      url: `/api/api-proxy/output/${asset.location.split(/[/\\]/).pop()}`,
    })
  }
}

function removeAsset(id: number) {
  selectedAssets.value = selectedAssets.value.filter((asset) => asset.id !== id)
}
const conversationItems = computed(() => {
  const items: Array<{ key: string; type: 'message'; index: number; message: ChatMessage } | { key: string; type: 'task'; task: WorkflowTask }> = []
  for (const [index, message] of messages.value.entries()) {
    items.push({ key: `message-${message.id ?? index}`, type: 'message', index, message })
    if (message.id != null) {
      for (const task of activeTasks.value.filter((entry) => entry.conversation_id === message.id)) {
        items.push({ key: task.execution_id, type: 'task', task })
      }
    }
  }
  for (const task of activeTasks.value) {
    if (task.conversation_id == null || !messages.value.some((message) => message.id === task.conversation_id)) {
      items.push({ key: task.execution_id, type: 'task', task })
    }
  }
  return items
})
const qualityLabels: Record<string, string> = { low: '低', medium: '中', high: '高' }
const parameterLabels: Record<string, string> = { n: '张数', aspect_ratio: '比例', quality: '质量', ratio: '比例', resolution: '分辨率', duration: '时长（秒）' }
const imageRatios = ['1:1', '16:9', '9:16', '4:3', '3:4'].map(value => ({ value, label: value }))
const videoRatios = ['16:9', '9:16', '1:1'].map(value => ({ value, label: value }))
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
    availableModels.value = []
    ElMessage.error('模型加载失败，请刷新后重试。')
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

async function deleteSessionFromList(sessionId: string) {
  if (isProcessing.value || !window.confirm('确定删除这个会话吗？')) return
  try {
    await deleteSession(sessionId)
    sessions.value = sessions.value.filter((session) => session.id !== sessionId)
    if (currentSessionId.value === sessionId) createNewSession()
  } catch (error) {
    console.error('删除会话失败:', error)
    ElMessage.error('删除会话失败，请稍后重试。')
  }
}

// 加载会话详情
async function loadSessionDetail(sessionId: string) {
  try {
    const detail = await getSessionHistory(sessionId)
    if (currentSessionId.value !== sessionId) return
    messages.value = detail.conversations as ChatMessage[]
    activeTasks.value = detail.tasks || []
    if (detail.generation_request) openGenerationDialog(detail.generation_request)
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
  selectedAssets.value = []
  generationType.value = 'none'
  generationDialogOpen.value = false
  await loadSessionDetail(sessionId)
}

// 创建新会话
function createNewSession() {
  if (isProcessing.value) return
  currentSessionId.value = undefined
  selectedAssets.value = []
  messages.value = []
  activeTasks.value = []
  generationType.value = 'none'
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
  generationType.value = 'none'
  await handleSubmit({ prompt: pendingGenerationPrompt.value, model, useWebSearch: false, attachedFile: null }, options)
}

// 处理消息提交
const handleSubmit = async (data: ChatSubmitData, confirmedOptions?: WorkflowMessageRequest['generation_options']) => {
  if (isProcessing.value) return
  lastSubmitData = data
  const submittedAssets = confirmedOptions ? [] : [...selectedAssets.value]
  console.log('用户提交:', data)

  // 乐观更新：立即添加用户消息到界面
  messages.value.push({
    role: 'user',
    message: data.prompt,
    assets: submittedAssets,
    created_at: new Date().toISOString(),
  })
  const userMessage = messages.value[messages.value.length - 1]!
  messages.value.push({
    role: 'agent',
    message: '',
    created_at: new Date().toISOString(),
  })
  const agentMessage = messages.value[messages.value.length - 1]!

  isProcessing.value = true

  try {
    // 调用后端 API
    const response = await sendWorkflowMessageStream(
      { message: data.prompt, model_id: Number(data.model.id), session_id: currentSessionId.value, generation_options: confirmedOptions, asset_ids: submittedAssets.map((asset) => asset.id) },
      (status) => {
        agentMessage.steps ??= []
        if (agentMessage.steps.at(-1) !== status) agentMessage.steps.push(status)
        console.info('[工作流对话]', status)
      },
      (text) => {
        const lastMessage = messages.value[messages.value.length - 1]
        if (lastMessage?.role === 'agent') lastMessage.message += text
      },
      (event) => {
        agentMessage.events ??= []
        agentMessage.events.push(event)
      },
      (usage) => { agentMessage.context_usage = usage },
    )
    agentMessage.context_usage = response.context_usage
    activeTasks.value = response.tasks || []
    if (!confirmedOptions) selectedAssets.value = []
    userMessage.id = response.user_conversation_id ?? undefined
    agentMessage.id = response.agent_conversation_id ?? undefined
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
    if (agentMessage?.role === 'agent' && !agentMessage.message) {
      agentMessage.message = response.reply
    }

    // 如果工作流准备就绪，刷新会话列表（状态可能已变化）
    if (response.workflow_ready && !sessionChanged) {
      await loadSessions()
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    const errorMessage = messages.value[messages.value.length - 1]
    if (errorMessage?.role === 'agent') {
      errorMessage.failed = true
      errorMessage.message = error instanceof Error ? error.message : '抱歉，处理您的请求时出现错误。'
    }
  } finally {
    isProcessing.value = false
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
.chat-page { display: flex; height: 100dvh; width: 100%; min-width: 0; background: transparent; color: var(--color-text); }
.sessions-sidebar { width: 244px; flex-shrink: 0; display: flex; flex-direction: column; border-right: 1px solid var(--color-border); background: var(--color-surface-soft); }
.sidebar-header { padding: 22px 16px; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.section-label { font-size: 12px; color: var(--color-muted); }
.sessions-list { overflow-y: auto; padding: 0 10px; }
.session-item { display: flex; align-items: center; gap: 4px; width: 100%; padding: 4px; margin-bottom: 5px; border: 1px solid transparent; border-radius: 8px; color: var(--color-muted); }
.session-item:hover, .session-item.active { background: var(--color-surface-soft); color: var(--color-text); }
.session-item.active { border-color: var(--color-border); }
.session-select { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; padding: 10px 6px; border: 0; background: transparent; text-align: left; color: inherit; }
.session-delete { display: grid; place-items: center; width: 30px; height: 30px; flex: 0 0 30px; border: 0; border-radius: 6px; background: transparent; color: var(--color-muted); opacity: 0; }
.session-item:hover .session-delete, .session-delete:focus-visible { opacity: 1; }
.session-delete:hover { color: var(--color-danger); }
.session-info { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.session-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.session-meta, .empty-sessions { color: var(--color-muted); font-size: 11px; }
.empty-sessions { padding: 20px 8px; }
.chat-content { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.chat-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 28px; border-bottom: 1px solid var(--color-border); }
.chat-header strong { font-size: 14px; font-weight: 500; }
.welcome-container { display: flex; flex: 1; flex-direction: column; align-items: center; justify-content: center; gap: 18px; padding: 32px 24px; text-align: center; }
.welcome-icon { width: 32px; height: 32px; margin-bottom: 8px; }
.welcome-container h1 { font-size: clamp(24px, 3vw, 32px); letter-spacing: -.04em; font-weight: 500; }
.welcome-container p { color: var(--color-muted); font-size: 14px; }
.welcome-suggestions { display: flex; justify-content: center; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.chat-conversation { min-height: 0; }
.conversation-inner { width: 100%; max-width: 840px; margin: 0 auto; padding: 36px 28px; gap: 28px; }
.chat-message { max-width: 100%; font-size: 14px; line-height: 1.8; }
.chat-message.is-user { align-items: flex-end; }
.message-author { display: flex; align-items: center; gap: 12px; font-size: 12px; color: var(--color-muted); }
.message-author span { font-size: 10px; opacity: .7; }
.message-row { border-radius: 10px; scroll-margin: 24px; }
.checkpoint-selected { outline: 1px solid var(--color-border-strong); outline-offset: 10px; }
.user-text { white-space: pre-wrap; overflow-wrap: anywhere; }
.execution-trace { margin: 8px 0; width: 100%; min-width: 0; max-width: 620px; }
.trace-tool { min-width: 0; }
.trace-tool :deep(pre) { max-height: 360px; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; }
.trace-tool :deep(pre), .trace-tool :deep(pre span) { color: var(--color-text) !important; background: transparent !important; }
.context-usage { display: grid; grid-template-columns: 1fr auto; gap: 8px 12px; font-size: 12px; }
.context-usage dt { color: var(--color-muted); }
.saved-checkpoint { margin-top: 14px; font-size: 11px; }
.saved-checkpoint :deep(button) { font-size: 11px; color: var(--color-muted); }
.generation-tool { width: 100%; }
.tool-details { padding: 0 16px 16px; display: flex; flex-direction: column; gap: 12px; }
.task-parameters { display: flex; flex-wrap: wrap; gap: 8px; color: var(--color-muted); font-size: 12px; }
.task-parameters dd { color: var(--color-text); margin-right: 14px; }
.task-meta { font-size: 11px; color: var(--color-muted); overflow-wrap: anywhere; }
.task-error { color: var(--color-danger); }
.task-images { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; max-width: 600px; margin-top: 10px; }
.task-images img, .task-images video { display: block; width: 100%; max-height: 420px; border-radius: 8px; object-fit: contain; }
.input-container { width: 100%; max-width: 840px; margin: 0 auto; padding: 12px 28px 22px; }
.chat-assets { display: flex; flex-wrap: wrap; gap: 10px; padding: 12px 12px 0; }
.chat-asset { display: flex; align-items: center; gap: 4px; border: 1px solid var(--color-border); border-radius: 8px; padding: 4px; }
.chat-asset img, .chat-asset video { width: 48px; height: 48px; object-fit: cover; border-radius: 4px; }
.pending-generation { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 12px; color: var(--color-muted); }
.generation-dialog-prompt { max-height: 140px; overflow: auto; font-size: 13px; line-height: 1.8; color: var(--color-muted); white-space: pre-wrap; }
.generation-dialog-fields { display: flex; flex-direction: column; gap: 16px; margin: 18px 0; }
.generation-dialog-fields label, .generation-choice { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; font-size: 12px; }
:global(.generation-dialog) { max-height: calc(100dvh - 48px); overflow-y: auto; }
:global(.context-panel) { width: 300px; max-height: 440px; overflow-y: auto; }
@media (max-width: 760px) {
  .sessions-sidebar { width: 174px; }
  .sidebar-header { flex-direction: column; align-items: stretch; padding: 16px 10px; }
  .chat-header { padding: 12px 16px; }
  .conversation-inner { padding: 24px 16px; }
  .input-container { padding: 12px 16px 16px; }
}
@media (max-width: 540px) {
  .chat-page { flex-direction: column; }
  .sessions-sidebar { width: 100%; max-height: 104px; border-right: 0; border-bottom: 1px solid var(--color-border); }
  .sidebar-header { flex-direction: row; align-items: center; padding: 8px 12px; }
  .sessions-list { display: flex; gap: 8px; padding-bottom: 6px; }
  .session-item { width: 150px; flex-shrink: 0; padding: 2px; margin: 0; }
  .session-delete { opacity: 1; }
  .session-meta { display: none; }
  .empty-sessions { padding: 4px; }
  .chat-content { min-height: 0; }
  .welcome-container { padding: 16px; gap: 12px; }
  .welcome-suggestions { flex-direction: column; margin-top: 4px; }
}
</style>
