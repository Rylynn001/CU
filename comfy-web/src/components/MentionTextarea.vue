<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElInput } from 'element-plus'

const props = withDefaults(defineProps<{
  modelValue: string
  rows?: number
  placeholder?: string
  disabled?: boolean
}>(), {
  rows: 4,
  placeholder: '',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'keyup', event: KeyboardEvent): void
  (e: 'keydown', event: KeyboardEvent): void
  (e: 'blur', event: FocusEvent): void
}>()

const inputRef = ref<InstanceType<typeof ElInput> | null>(null)
const highlightRef = ref<HTMLElement | null>(null)
const textarea = computed(() => inputRef.value?.textarea)
const isComposing = ref(false)
let resizeObserver: ResizeObserver | undefined

function syncHighlightLayout() {
  const input = textarea.value
  const highlight = highlightRef.value
  if (!input || !highlight) return
  // 外层页面会覆盖输入框样式，高亮层必须使用真实输入框的排版和可视宽度。
  const style = getComputedStyle(input)
  for (const property of ['padding', 'border-width', 'font-family', 'font-size', 'font-weight', 'font-style', 'line-height', 'letter-spacing', 'text-indent', 'text-align', 'word-break', 'overflow-wrap', 'tab-size']) {
    highlight.style.setProperty(property, style.getPropertyValue(property))
  }
  highlight.style.width = `${input.clientWidth + parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth)}px`
  highlight.style.height = `${input.clientHeight + parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth)}px`
  highlight.scrollTop = input.scrollTop
  highlight.scrollLeft = input.scrollLeft
}

function startComposition() {
  isComposing.value = true
}

function endComposition() {
  isComposing.value = false
}

function escapeHtml(value: string) {
  const div = document.createElement('div')
  div.textContent = value
  return div.innerHTML
}

const highlightedText = computed(() => {
  const escaped = escapeHtml(props.modelValue)
  return escaped.replace(
    /@(视频|图片|图)\d+/g,
    mention => `<mark class="mention-token ${mention.startsWith('@视频') ? 'video' : 'image'}">${mention}</mark>`,
  )
})

function syncScroll() {
  const input = textarea.value
  const highlight = highlightRef.value
  if (!input || !highlight) return
  highlight.scrollTop = input.scrollTop
  highlight.scrollLeft = input.scrollLeft
}

watch(() => props.modelValue, () => nextTick(syncHighlightLayout), { flush: 'post' })

onMounted(() => nextTick(() => {
  const input = textarea.value
  if (!input) return
  input.addEventListener('scroll', syncScroll)
  resizeObserver = new ResizeObserver(syncHighlightLayout)
  resizeObserver.observe(input)
  syncHighlightLayout()
}))
onBeforeUnmount(() => {
  textarea.value?.removeEventListener('scroll', syncScroll)
  resizeObserver?.disconnect()
})

defineExpose({ textarea })
</script>

<template>
  <div class="mention-textarea" :class="{ composing: isComposing }">
    <pre
      v-if="modelValue"
      ref="highlightRef"
      class="mention-highlight"
      aria-hidden="true"
      v-html="highlightedText"
    />
    <ElInput
      ref="inputRef"
      class="mention-textarea-input"
      type="textarea"
      :rows="rows"
      :model-value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      @update:model-value="emit('update:modelValue', $event)"
      @keyup="emit('keyup', $event)"
      @keydown="emit('keydown', $event)"
      @compositionstart="startComposition"
      @compositionend="endComposition"
      @blur="emit('blur', $event)"
    />
  </div>
</template>

<style scoped>
.mention-textarea {
  position: relative;
  width: 100%;
  border-radius: var(--radius-md, 8px);
  background: rgba(var(--color-white-rgb), 0.035);
}

.mention-highlight {
  position: absolute;
  inset: 0;
  z-index: 0;
  box-sizing: border-box;
  border: 0 solid transparent;
  margin: 0;
  padding: 5px 11px;
  overflow: hidden;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  word-break: break-word;
  pointer-events: none;
  color: var(--color-text);
  font-family: inherit;
  font-size: var(--el-font-size-base, 14px);
  line-height: 1.5;
  letter-spacing: 0;
  font-variant-ligatures: none;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.mention-highlight :deep(.mention-token) {
  display: inline;
  border-radius: 3px;
  color: inherit;
  font: inherit;
  letter-spacing: 0;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}

.mention-highlight :deep(.mention-token.image) {
  color: var(--color-info);
  background: rgba(var(--color-success-rgb), 0.2);
  box-shadow: 0 0 0 2px rgba(var(--color-success-rgb), 0.2);
}

.mention-highlight :deep(.mention-token.video) {
  color: var(--color-warning);
  background: rgba(var(--color-danger-rgb), 0.2);
  box-shadow: 0 0 0 2px rgba(var(--color-danger-rgb), 0.2);
}

.mention-textarea-input {
  position: relative;
  z-index: 1;
}

.mention-textarea-input :deep(.el-textarea__inner) {
  color: transparent;
  -webkit-text-fill-color: transparent;
  caret-color: var(--color-text);
  background: transparent;
  font-variant-ligatures: none;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.mention-textarea-input :deep(.el-textarea__inner::placeholder) {
  color: var(--color-faint);
  -webkit-text-fill-color: var(--color-faint);
}

/* 输入法组合拼音需要显示在真实输入框中，避免被高亮层的透明文字样式遮住。 */
.mention-textarea.composing .mention-highlight {
  visibility: hidden;
}

.mention-textarea.composing .mention-textarea-input :deep(.el-textarea__inner) {
  color: var(--color-text);
  -webkit-text-fill-color: var(--color-text);
}
</style>
