<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { PaperclipIcon, ArrowUpIcon, LoaderCircleIcon, SquareIcon } from '@lucide/vue'
import { PromptInput, PromptInputTextarea, PromptInputFooter, PromptInputTools, PromptInputButton, PromptInputSubmit } from '@/components/ai-elements/prompt-input'
import { usePromptInputProvider } from '@/components/ai-elements/prompt-input/context'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Context, ContextTrigger, ContextIcon, ContextContent, ContextContentHeader, ContextContentBody } from '@/components/ai-elements/context'
import type { ContextUsage } from '@/api/workflow'
import type { AIModel, ChatSubmitData } from '@/types/ai-models'
import mediaReferenceInput from './mediaReferenceInput.vue'
import type { CanvasReference } from '../services/canvasGraph'

const props = withDefaults(defineProps<{
  models?: AIModel[]
  isProcessing?: boolean
  canStop?: boolean
  previewOnly?: boolean
  assetCount?: number
  skillId?: string
  requiresSkill?: boolean
  contextUsage?: ContextUsage | null
  references?: CanvasReference[]
  onSubmit?: (data: ChatSubmitData) => Promise<unknown>
}>(), { models: () => [], assetCount: 0, references: () => [] })
const emit = defineEmits<{ assets: []; stop: [] }>()
const root = ref<HTMLElement>()
const modelId = ref<string>('')
watch(() => props.models, models => {
  if (!models.some(model => model.id === modelId.value)) modelId.value = models[0]?.id ?? ''
}, { immediate: true })
const selectedModel = computed(() => props.models.find(model => model.id === modelId.value))
const skillPrefixes: Record<string, string> = {
  'gpt-image-2-style-library': '使用 gpt-image-2-style-library 技能优化以下提示词，只要文字，不生成图片：\n\n',
  'seedance-prompt': '使用 Seedance 技能优化以下提示词，只要文字，不生成视频或图片：\n\n',
  'image-prompt-reverse': '请使用图片提示词反推技能，根据引用的图片反推提示词，只返回文字，不生成图片或视频：\n\n',
}
function hasPrompt(text: string) {
  const prefix = skillPrefixes[props.skillId || '']
  return (prefix && text.startsWith(prefix) ? text.slice(prefix.length) : text).trim().length > 0
}
const { textInput, setTextInput } = usePromptInputProvider({
  maxFiles: 0,
  onError: () => ElMessage.info(props.previewOnly ? '当前仅支持文字草稿。' : '请通过回形针按钮引入参考资产。'),
  onSubmit: async ({ text }) => {
    if (props.previewOnly || props.isProcessing || (props.requiresSkill && !props.skillId) || !hasPrompt(text) || !selectedModel.value) {
      setTextInput(text)
      return
    }
    await props.onSubmit?.({ prompt: text.trim(), skillId: props.skillId || undefined, model: selectedModel.value, useWebSearch: false, attachedFile: null })
  },
})
const disabled = computed(() => props.previewOnly || props.isProcessing || (props.requiresSkill && !props.skillId) || !hasPrompt(textInput.value) || !selectedModel.value)
watch(() => props.skillId, (skillId, previousId) => {
  const previousPrefix = skillPrefixes[previousId || '']
  const content = previousPrefix && textInput.value.startsWith(previousPrefix)
    ? textInput.value.slice(previousPrefix.length) : textInput.value
  const prefix = skillPrefixes[skillId || ''] || ''
  setTextInput(prefix && content.startsWith(prefix) ? content : prefix + content)
  if (prefix) nextTick(focus)
}, { flush: 'sync', immediate: true })
const usage = computed(() => props.contextUsage?.model === selectedModel.value?.name ? props.contextUsage : undefined)
const maxTokens = computed(() => selectedModel.value?.contextWindow ?? usage.value?.max_tokens ?? 0)
const hasUsage = computed(() => usage.value?.used_tokens != null)
function focus() { root.value?.querySelector('textarea')?.focus() }
function setPrompt(text: string) { setTextInput(text); focus() }
function onPromptKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || disabled.value) return
  event.preventDefault()
  root.value?.querySelector('form')?.requestSubmit()
}
defineExpose({ focus, setPrompt, selectedModel })
</script>

<template>
  <div ref="root" class="ai-elements ai-composer">
    <PromptInput :max-files="0">
      <slot name="attachments" />
      <mediaReferenceInput v-if="!previewOnly" :model-value="textInput" :items="references" :show-references="false"
        :disabled="isProcessing" placeholder="描述你的想法，输入 @ 引用画布素材…" @update:model-value="setTextInput" @keydown="onPromptKeydown" />
      <PromptInputTextarea v-else aria-label="消息内容" placeholder="描述你的想法…" :disabled="isProcessing" />
      <PromptInputFooter v-if="$slots.workspace" class="composer-workspace-row">
        <PromptInputTools>
          <PromptInputButton aria-label="引入参考资产" title="引入参考资产" :disabled="isProcessing || assetCount >= 10" @click="emit('assets')"><PaperclipIcon class="size-4" /></PromptInputButton>
          <slot name="workspace" />
        </PromptInputTools>
      </PromptInputFooter>
      <PromptInputFooter class="composer-controls">
        <PromptInputTools class="composer-tools">
          <PromptInputButton v-if="!previewOnly && !$slots.workspace" aria-label="引入参考资产" title="引入参考资产" :disabled="isProcessing || assetCount >= 10" @click="emit('assets')"><PaperclipIcon class="size-4" /></PromptInputButton>
          <slot name="skills" />
          <div class="composer-model-context">
          <Select v-if="models.length" v-model="modelId" :disabled="isProcessing">
            <SelectTrigger class="composer-model h-8 border-0 bg-transparent shadow-none" aria-label="对话模型" :title="selectedModel?.name"><SelectValue placeholder="选择模型" /></SelectTrigger>
            <SelectContent class="ai-elements"><SelectItem v-for="model in models" :key="model.id" :value="model.id">{{ model.name }}</SelectItem></SelectContent>
          </Select>
          <span v-else class="composer-hint">{{ previewOnly ? '提示词草稿' : '暂无可用模型' }}</span>
          <Context v-if="selectedModel && !previewOnly" :used-tokens="usage?.used_tokens ?? 0" :max-tokens="maxTokens">
            <ContextTrigger class="composer-context" aria-label="上下文用量">
              <template v-if="!hasUsage || !maxTokens" #default>
                <PromptInputButton class="composer-context" aria-label="上下文用量"><span>—</span><ContextIcon /></PromptInputButton>
              </template>
            </ContextTrigger>
            <ContextContent class="ai-elements" side="top" align="end">
              <ContextContentHeader v-if="hasUsage && maxTokens" />
              <ContextContentBody class="context-details">
                <p class="context-title">上下文用量</p>
                <dl>
                  <div><dt>模型容量</dt><dd>{{ maxTokens ? maxTokens.toLocaleString() : '未配置' }}</dd></div>
                  <div><dt>本轮用量</dt><dd>{{ usage?.used_tokens?.toLocaleString() ?? '暂无数据' }}</dd></div>
                  <div><dt>输入</dt><dd>{{ usage?.input_tokens?.toLocaleString() ?? '—' }}</dd></div>
                  <div><dt>输出</dt><dd>{{ usage?.output_tokens?.toLocaleString() ?? '—' }}</dd></div>
                </dl>
              </ContextContentBody>
            </ContextContent>
          </Context>
          </div>
        </PromptInputTools>
        <PromptInputButton v-if="canStop" variant="default" aria-label="停止运行" title="停止运行" @click="emit('stop')"><SquareIcon class="size-4" /></PromptInputButton>
        <PromptInputSubmit v-else :disabled="disabled" :status="isProcessing ? 'submitted' : 'ready'" :aria-label="previewOnly ? '暂未开放发送' : '发送消息'" :title="previewOnly ? '仅展示，暂不发送' : '发送消息'">
          <template v-if="$slots.workspace" #default><LoaderCircleIcon v-if="isProcessing" class="size-4 animate-spin" /><ArrowUpIcon v-else class="size-4" /></template>
        </PromptInputSubmit>
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
.composer-controls { min-width: 0; }
.composer-tools { flex: 1; min-width: 0; flex-wrap: wrap; }
.composer-model-context { display: flex; align-items: center; min-width: 0; flex: 1 1 140px; }
.composer-model { min-width: 0; max-width: min(160px, 40vw); flex-shrink: 1; }
.composer-model :deep([data-slot="select-value"]) { display: block; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.composer-context { flex-shrink: 0; height: 32px; gap: 4px; padding: 0 6px; color: var(--color-muted); font-size: 12px; }
.context-title { margin-bottom: 8px; font-size: 12px; font-weight: 500; }
.context-details dl { display: grid; gap: 6px; font-size: 12px; }
.context-details dl > div { display: flex; justify-content: space-between; gap: 16px; }
.context-details dt { color: var(--color-muted); }
</style>
