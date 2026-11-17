<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { PaperclipIcon } from '@lucide/vue'
import { PromptInput, PromptInputTextarea, PromptInputFooter, PromptInputTools, PromptInputButton, PromptInputSubmit, PromptInputSpeechButton } from '@/components/ai-elements/prompt-input'
import { usePromptInputProvider } from '@/components/ai-elements/prompt-input/context'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { AIModel, ChatSubmitData } from '@/types/ai-models'
import mediaReferenceInput from './mediaReferenceInput.vue'
import type { CanvasReference } from '../services/canvasGraph'

const props = withDefaults(defineProps<{
  models?: AIModel[]
  isProcessing?: boolean
  previewOnly?: boolean
  assetCount?: number
  references?: CanvasReference[]
  onSubmit?: (data: ChatSubmitData) => Promise<void>
}>(), { models: () => [], assetCount: 0, references: () => [] })
const emit = defineEmits<{ assets: [] }>()
const root = ref<HTMLElement>()
const modelId = ref<string>('')
watch(() => props.models, models => {
  if (!models.some(model => model.id === modelId.value)) modelId.value = models[0]?.id ?? ''
}, { immediate: true })
const selectedModel = computed(() => props.models.find(model => model.id === modelId.value))
const { textInput, setTextInput } = usePromptInputProvider({
  maxFiles: 0,
  onError: () => ElMessage.info(props.previewOnly ? '当前仅支持文字草稿。' : '请通过回形针按钮引入参考资产。'),
  onSubmit: async ({ text }) => {
    if (props.previewOnly || props.isProcessing || !text.trim() || !selectedModel.value) {
      setTextInput(text)
      return
    }
    await props.onSubmit?.({ prompt: text.trim(), model: selectedModel.value, useWebSearch: false, attachedFile: null })
  },
})
const disabled = computed(() => props.previewOnly || props.isProcessing || !textInput.value.trim() || !selectedModel.value)
function focus() { root.value?.querySelector('textarea')?.focus() }
function setPrompt(text: string) { setTextInput(text); focus() }
function onPromptKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || disabled.value) return
  event.preventDefault()
  root.value?.querySelector('form')?.requestSubmit()
}
defineExpose({ focus, setPrompt })
</script>

<template>
  <div ref="root" class="ai-elements ai-composer">
    <PromptInput :max-files="0">
      <slot name="attachments" />
      <mediaReferenceInput v-if="!previewOnly" :model-value="textInput" :items="references" :show-references="false"
        :disabled="isProcessing" placeholder="描述你的想法，输入 @ 引用画布素材…" @update:model-value="setTextInput" @keydown="onPromptKeydown" />
      <PromptInputTextarea v-else aria-label="消息内容" placeholder="描述你的想法…" :disabled="isProcessing" />
      <PromptInputFooter>
        <PromptInputTools>
          <PromptInputButton v-if="!previewOnly" aria-label="引入参考资产" title="引入参考资产" :disabled="isProcessing || assetCount >= 10" @click="emit('assets')"><PaperclipIcon class="size-4" /></PromptInputButton>
          <PromptInputSpeechButton aria-label="语音输入" title="语音输入" :disabled="isProcessing" />
          <Select v-if="models.length" v-model="modelId" :disabled="isProcessing">
            <SelectTrigger class="h-8 max-w-48 border-0 bg-transparent shadow-none" aria-label="对话模型"><SelectValue placeholder="选择模型" /></SelectTrigger>
            <SelectContent class="ai-elements"><SelectItem v-for="model in models" :key="model.id" :value="model.id">{{ model.name }}</SelectItem></SelectContent>
          </Select>
          <span v-else class="composer-hint">{{ previewOnly ? '提示词草稿' : '暂无可用模型' }}</span>
        </PromptInputTools>
        <PromptInputSubmit :disabled="disabled" :status="isProcessing ? 'submitted' : 'ready'" :aria-label="previewOnly ? '暂未开放发送' : '发送消息'" :title="previewOnly ? '仅展示，暂不发送' : '发送消息'" />
      </PromptInputFooter>
    </PromptInput>
    <p class="composer-hint composer-footnote">{{ previewOnly ? '当前为输入预览，内容不会发送。' : '回车发送 · 换行请按 Shift + 回车' }}</p>
  </div>
</template>

<style scoped>
.ai-composer { width: 100%; }
.composer-hint { color: var(--color-muted); font-size: 12px; }
.composer-footnote { margin-top: 10px; text-align: center; }
.ai-composer :deep([data-slot="input-group"]) { overflow: visible; background: var(--color-surface); backdrop-filter: var(--glass-blur); border-radius: 16px; }
.ai-composer :deep(.reference-input) { width: 100%; }
.ai-composer :deep(textarea) { padding: 18px; font-size: 14px; }
</style>
