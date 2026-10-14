<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElInput } from 'element-plus'

const props = withDefaults(defineProps<{
  modelValue: string
  rows?: number
  placeholder?: string
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
const lastScrollTop = ref(0)
const lastScrollLeft = ref(0)

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
  lastScrollTop.value = input.scrollTop
  lastScrollLeft.value = input.scrollLeft
  requestAnimationFrame(() => {
    highlight.scrollTop = input.scrollTop
    highlight.scrollLeft = input.scrollLeft
  })
}

function restoreScroll() {
  const input = textarea.value
  const highlight = highlightRef.value
  if (!input || !highlight) return
  nextTick(() => {
    input.scrollTop = lastScrollTop.value
    input.scrollLeft = lastScrollLeft.value
    highlight.scrollTop = lastScrollTop.value
    highlight.scrollLeft = lastScrollLeft.value
  })
}

watch(() => props.modelValue, () => {
  restoreScroll()
})

onMounted(() => nextTick(() => textarea.value?.addEventListener('scroll', syncScroll)))

defineExpose({ textarea })
</script>

<template>
  <div class="mention-textarea">
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
      @update:model-value="emit('update:modelValue', $event)"
      @keyup="emit('keyup', $event)"
      @keydown="emit('keydown', $event)"
      @blur="emit('blur', $event)"
    />
  </div>
</template>

<style scoped>
.mention-textarea {
  position: relative;
  width: 100%;
  border-radius: var(--radius-md, 8px);
  background: rgba(255, 255, 255, 0.035);
}

.mention-highlight {
  position: absolute;
  inset: 0;
  z-index: 0;
  box-sizing: border-box;
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
  display: inline-block;
  border-radius: 3px;
  color: inherit;
  font: inherit;
  letter-spacing: 0;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}

.mention-highlight :deep(.mention-token.image) {
  color: #6ee7d8;
  background: rgba(20, 184, 166, 0.2);
  box-shadow: 0 0 0 2px rgba(20, 184, 166, 0.2);
}

.mention-highlight :deep(.mention-token.video) {
  color: #fcd27a;
  background: rgba(245, 158, 11, 0.2);
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2);
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
</style>
