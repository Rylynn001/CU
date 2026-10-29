<template>
  <div :class="['ai-input', containerClassName]">
    <Transition name="welcome">
      <div v-if="showWelcome && !isTyping" class="welcome-row">
        <RobotBeta emotion="reading" :is-listening="isListening" />
        <div>
          <h2>{{ title }}</h2>
          <p v-if="subtitle">{{ subtitle }}</p>
        </div>
      </div>
    </Transition>

    <div class="composer-wrap" :class="{ typing: isTyping }">
      <Transition name="robot-float">
        <div v-if="isTyping" class="floating-robot">
          <RobotBeta :emotion="isSending ? 'thinking' : 'reading'" :text-length="prompt.length" :is-listening="isListening" />
        </div>
      </Transition>

      <section class="composer-card" :class="[className, { disabled }]">
        <el-tag v-if="file" class="attachment-tag" closable @close="file = null">
          <IconComponents :name="file.isImage ? 'image' : 'file'" :size="14" />
          <span>{{ file.name }}</span>
        </el-tag>

        <el-input
          v-model="prompt"
          class="prompt-input"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 8 }"
          :disabled="disabled"
          :placeholder="placeholderText"
          @keydown.enter="onEnter"
        />

        <div class="composer-toolbar">
          <div class="toolbar-tools">
            <el-popover v-model:visible="modelMenuOpen" placement="top-start" :width="320" :teleported="false">
              <template #reference>
                <el-button class="model-trigger" :disabled="disabled">
                  <AIProviderIcons :name="selectedModel.iconName" :size="15" :class="selectedModel.badgeColor" />
                  <span class="model-name">{{ selectedModel.name }}</span>
                  <el-tag class="model-effort" size="small" effect="plain">{{ currentEffort.label }}</el-tag>
                  <IconComponents name="caret-down" :size="12" />
                </el-button>
              </template>

              <div class="model-menu">
                <h3>AI 模型</h3>
                <div class="model-list">
                  <el-button
                    v-for="model in models"
                    :key="model.id"
                    class="model-option"
                    :class="{ selected: selectedModel.id === model.id }"
                    @click="selectModel(model)"
                  >
                    <AIProviderIcons :name="model.iconName" :size="17" :class="model.badgeColor" />
                    <span class="model-option-copy">
                      <span class="model-option-title">
                        {{ model.name }}
                        <el-tag v-if="model.tag" size="small" effect="plain">{{ model.tag }}</el-tag>
                      </span>
                      <small>{{ model.provider }} · {{ (modelEfforts[model.id] || model.defaultLevel).toUpperCase() }}</small>
                    </span>
                    <IconComponents v-if="selectedModel.id === model.id" name="check" :size="14" />
                  </el-button>
                </div>

                <div class="effort-setting">
                  <div class="effort-heading">
                    <span>{{ selectedModel.reasoningTitle }}</span>
                    <strong>{{ currentEffort.label }}</strong>
                  </div>
                  <SegmentedControl
                    :model-value="effortId"
                    :options="effortOptions"
                    :label="selectedModel.reasoningTitle"
                    :disabled="disabled"
                    @update:model-value="setEffort"
                  />
                  <p>{{ currentEffort.desc }}</p>
                  <p>当前聊天接口尚未启用推理强度设置。</p>
                </div>
              </div>
            </el-popover>

            <input ref="fileInput" class="file-input" type="file" :disabled="disabled" @change="onFileChange" />
            <el-tooltip v-if="enableAttachments" content="附加照片或文件">
              <el-button text circle :disabled="disabled" aria-label="附加照片或文件" @click="fileInput?.click()">
                <IconComponents name="paperclip" :size="17" />
              </el-button>
            </el-tooltip>

            <el-button
              v-if="enableWebSearch"
              text
              :type="searchEnabled ? 'success' : 'default'"
              :disabled="disabled"
              @click="searchEnabled = !searchEnabled"
            >
              <IconComponents name="globe" :size="16" />
              {{ searchEnabled ? '搜索激活' : '搜索' }}
            </el-button>
          </div>

          <div class="toolbar-actions">
            <Transition name="voice-wave">
              <div v-if="isListening" class="voice-wave" title="语音输入激活">
                <span v-for="(bar, index) in voiceBars" :key="index" :style="waveStyle(index)" />
              </div>
            </Transition>
            <el-tooltip v-if="enableVoice" :content="isListening ? '停止语音输入' : '语音输入'">
              <el-button text circle :type="isListening ? 'danger' : 'default'" :disabled="disabled" aria-label="语音输入" @click="toggleVoice">
                <IconComponents :name="isListening ? 'microphone-fill' : 'microphone'" :size="17" />
              </el-button>
            </el-tooltip>
            <el-tooltip :content="isSending ? '点击取消' : '发送消息'">
              <el-button
                type="primary"
                circle
                :loading="isSending"
                :disabled="disabled || (!isSending && !canSend)"
                :aria-label="isSending ? '取消消息' : '发送消息'"
                @click="isSending ? cancelSend() : submit()"
              >
                <IconComponents v-if="!isSending" name="arrow-up" :size="17" />
              </el-button>
            </el-tooltip>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import RobotBeta from './RobotBeta.vue'
import AIProviderIcons from './icons/AIProviderIcons.vue'
import IconComponents from './icons/IconComponents.vue'
import SegmentedControl from './SegmentedControl.vue'
import type { AIModel, AttachedFile, ChatSubmitData } from '@/types/ai-models'
import { DEFAULT_AI_MODELS } from '@/types/ai-models'

const props = withDefaults(defineProps<{
  onSubmit?: (data: ChatSubmitData) => void | Promise<void>
  isProcessing?: boolean
  value?: string
  onChange?: (value: string) => void
  disabled?: boolean
  placeholder?: string
  title?: string
  subtitle?: string
  showWelcome?: boolean
  models?: AIModel[]
  defaultModelId?: string
  enableVoice?: boolean
  enableWebSearch?: boolean
  enableAttachments?: boolean
  className?: string
  containerClassName?: string
}>(), {
  disabled: false,
  placeholder: '我能为您做什么？输入或语音输入...',
  title: '我能为您做什么？',
  subtitle: '输入提示词或语音输入开始对话',
  showWelcome: true,
  models: () => DEFAULT_AI_MODELS,
  defaultModelId: 'gpt-5',
  enableVoice: true,
  enableWebSearch: true,
  enableAttachments: true,
  className: '',
  containerClassName: '',
})

const internalPrompt = ref('')
const prompt = computed({
  get: () => props.value ?? internalPrompt.value,
  set: (value: string) => {
    internalPrompt.value = value
    props.onChange?.(value)
  },
})
const searchEnabled = ref(false)
const sending = ref(false)
const modelMenuOpen = ref(false)
const file = ref<AttachedFile | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const selectedModel = ref(props.models.find((model) => model.id === props.defaultModelId) || props.models[0] || DEFAULT_AI_MODELS[0])
const modelEfforts = ref<Record<string, string>>(Object.fromEntries(props.models.map((model) => [model.id, model.defaultLevel])))
const effortId = computed(() => modelEfforts.value[selectedModel.value.id] || selectedModel.value.defaultLevel)
const currentEffort = computed(() => selectedModel.value.levels.find((level) => level.id === effortId.value) || selectedModel.value.levels[0])
const effortOptions = computed(() => selectedModel.value.levels.map((level) => ({ value: level.id, label: level.label })))
const isSending = computed(() => props.isProcessing ?? sending.value)
const isListening = ref(false)
const isTyping = computed(() => Boolean(prompt.value || file.value || isListening.value))
const canSend = computed(() => Boolean(prompt.value.trim() || file.value))
const placeholderText = computed(() => isListening.value ? '正在聆听您的语音...' : isSending.value ? '正在处理中...' : props.placeholder)
const voiceBars = [4, 7, 10, 6, 4]
let recognition: any = null
let sendTimer: ReturnType<typeof setTimeout> | null = null

function selectModel(model: AIModel) {
  selectedModel.value = model
  modelMenuOpen.value = false
}

function setEffort(level: string) {
  modelEfforts.value[selectedModel.value.id] = level
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = input.files?.[0]
  if (selected) file.value = { name: selected.name, isImage: selected.type.startsWith('image/'), file: selected }
  input.value = ''
}

function onEnter(event: KeyboardEvent) {
  if (!event.shiftKey) {
    event.preventDefault()
    submit()
  }
}

async function submit() {
  if (props.disabled || !canSend.value || isSending.value) return
  stopVoice()
  const data: ChatSubmitData = {
    prompt: prompt.value.trim(),
    model: selectedModel.value,
    effort: effortId.value,
    useWebSearch: searchEnabled.value,
    attachedFile: file.value,
  }
  if (props.onSubmit) {
    sending.value = true
    try {
      await props.onSubmit(data)
    } finally {
      sending.value = false
      prompt.value = ''
      file.value = null
    }
    return
  }
  sending.value = true
  sendTimer = setTimeout(() => {
    sending.value = false
    prompt.value = ''
    file.value = null
    sendTimer = null
  }, (currentEffort.value?.multiplier || 2.8) * 1000 + (searchEnabled.value ? 900 : 0))
}

function cancelSend() {
  if (sendTimer) clearTimeout(sendTimer)
  sendTimer = null
  sending.value = false
  stopVoice()
}

function toggleVoice() {
  if (isListening.value) {
    stopVoice()
    return
  }
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SpeechRecognition) return
  recognition = new SpeechRecognition()
  recognition.lang = navigator.language || 'zh-CN'
  recognition.continuous = true
  recognition.interimResults = true
  recognition.onresult = (event: any) => {
    let text = ''
    for (let index = 0; index < event.results.length; index++) text += event.results[index][0].transcript
    if (text) prompt.value = text
  }
  recognition.onend = () => { isListening.value = false }
  recognition.onerror = () => stopVoice()
  recognition.start()
  isListening.value = true
}

function stopVoice() {
  isListening.value = false
  if (recognition) {
    try { recognition.stop() } catch { /* 识别可能已结束 */ }
    recognition = null
  }
}

function waveStyle(index: number) {
  return { height: `${voiceBars[index]}px`, animationDelay: `${index * 0.08}s` }
}

onUnmounted(() => {
  stopVoice()
  if (sendTimer) clearTimeout(sendTimer)
})
</script>

<style scoped>
.ai-input { width: 100%; color: var(--color-text); }
.welcome-row { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.welcome-row h2 { margin: 0; color: var(--color-text); font-size: 24px; font-weight: 700; line-height: 1.25; }
.welcome-row p { margin: 4px 0 0; color: var(--color-text-soft); font-size: 14px; }
.robot-slot { flex: 0 0 auto; }
.composer-wrap { position: relative; width: 100%; transition: padding-top .3s ease; }
.composer-wrap.typing { padding-top: 72px; }
.floating-robot { position: absolute; z-index: 2; top: 4px; right: 20px; pointer-events: none; }
.composer-card { position: relative; z-index: 1; width: 100%; padding: 16px 20px; border: 1px solid rgba(var(--color-white-rgb), .12); border-radius: 24px; background: var(--color-bg); box-shadow: 0 20px 50px rgba(var(--color-black-rgb), .45); transition: border-color .2s, box-shadow .2s; }
.composer-card:focus-within { border-color: rgba(var(--color-white-rgb), .3); box-shadow: 0 24px 56px rgba(var(--color-black-rgb), .52); }
.composer-card.disabled { opacity: .6; }
.attachment-tag { display: inline-flex; max-width: 100%; margin-bottom: 8px; }
.attachment-tag span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.prompt-input { margin-bottom: 14px; }
.prompt-input :deep(.el-textarea__inner) { min-height: 96px !important; max-height: 260px; padding: 4px 0; resize: none; border: 0 !important; background: transparent !important; box-shadow: none !important; color: var(--color-text) !important; font-size: 16px; line-height: 1.55; }
.prompt-input :deep(.el-textarea__inner::placeholder) { color: var(--color-muted) !important; }
.composer-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 12px; border-top: 1px solid rgba(var(--color-white-rgb), .1); }
.toolbar-tools, .toolbar-actions { display: flex; align-items: center; gap: 6px; min-width: 0; }
.toolbar-actions { flex: 0 0 auto; }
.model-selector { min-width: 0; }
.model-trigger { display: inline-flex; max-width: 280px; align-items: center; gap: 7px; padding: 7px 10px; border: 0; border-radius: 999px; background: rgba(var(--color-white-rgb), .08); color: var(--color-text); }
.model-trigger:hover { background: rgba(var(--color-white-rgb), .14); color: var(--color-white); }
.model-trigger :deep(> span) { min-width: 0; gap: 7px; }
.model-effort { flex-shrink: 0; background: rgba(var(--color-white-rgb), .08); border-color: var(--color-border); color: var(--color-text); }
.model-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-menu h3 { margin: 0 0 8px; color: var(--color-text-soft); font-size: 11px; font-weight: 700; }
.model-list { display: grid; gap: 3px; }
.model-option { display: flex; width: 100%; height: auto; justify-content: flex-start; gap: 10px; padding: 8px; border: 0; text-align: left; white-space: normal; }
.model-option.selected, .model-option:hover { background: rgba(var(--color-white-rgb), .08); }
.model-option-copy { display: grid; flex: 1; gap: 3px; min-width: 0; }
.model-option-title { display: flex; align-items: center; gap: 6px; color: var(--color-text); font-size: 12px; font-weight: 600; }
.model-option-meta { color: var(--color-text-soft); font-size: 10px; }
.effort-setting { margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(var(--color-white-rgb), .1); }
.effort-heading { display: flex; justify-content: space-between; margin-bottom: 8px; color: var(--color-text-soft); font-size: 11px; }
.effort-heading strong { color: var(--color-text); }
.effort-setting p { margin: 7px 0 0; color: var(--color-text-soft); font-size: 11px; }
.file-input { display: none; }
.voice-wave { display: flex; align-items: center; gap: 4px; height: 32px; padding: 0 10px; border: 1px solid rgba(var(--color-danger-rgb), .25); border-radius: 12px; background: rgba(var(--color-danger-rgb), .1); }
.voice-wave span { width: 4px; border-radius: 4px; background: var(--color-danger); animation: wave .5s ease-in-out infinite alternate; }
.voice-wave span:nth-child(even) { animation-duration: .7s; }
@keyframes wave { to { transform: scaleY(.45); } }
.welcome-enter-active, .welcome-leave-active, .robot-float-enter-active, .robot-float-leave-active, .voice-wave-enter-active, .voice-wave-leave-active { transition: opacity .2s, transform .2s; }
.welcome-enter-from, .welcome-leave-to, .robot-float-enter-from, .robot-float-leave-to, .voice-wave-enter-from, .voice-wave-leave-to { opacity: 0; transform: translateY(6px); }
:deep(.el-popper) { --el-bg-color-overlay: var(--color-bg); --el-border-color-light: rgba(var(--color-white-rgb), .12); color: var(--color-text); }
@media (max-width: 640px) {
  .welcome-row { align-items: flex-start; gap: 12px; }
  .welcome-row h2 { font-size: 20px; }
  .composer-card { padding: 14px; border-radius: 20px; }
  .composer-toolbar { align-items: flex-start; }
  .toolbar-tools { flex-wrap: wrap; }
  .model-trigger { max-width: 210px; }
}
</style>
