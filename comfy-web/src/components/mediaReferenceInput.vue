<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import MentionTextarea from './MentionTextarea.vue'
import type { CanvasReference } from '../services/canvasGraph'

const props = withDefaults(defineProps<{
  modelValue: string
  items: CanvasReference[]
  disabled?: boolean
  rows?: number
  placeholder?: string
  showReferences?: boolean
}>(), { rows: 3, showReferences: true, placeholder: '描述你想生成的内容（输入 @ 引用素材）' })
const emit = defineEmits<{
  'update:modelValue': [value: string]
  keydown: [event: KeyboardEvent]
}>()
const input = ref<InstanceType<typeof MentionTextarea>>()
const start = ref(-1)
const query = ref('')
const activeIndex = ref(0)
const matches = computed(() => props.items.filter(item => item.url && `${item.label} ${item.mention}`.toLowerCase().includes(query.value.toLowerCase())))
const open = computed(() => start.value >= 0 && matches.value.length > 0 && !props.disabled)

function close() { start.value = -1 }
function update(value: string) {
  emit('update:modelValue', value)
  const textarea = input.value?.textarea
  const before = value.slice(0, textarea?.selectionStart ?? value.length)
  const match = before.match(/@([^@\s]*)$/)
  start.value = match ? before.length - match[0].length : -1
  query.value = match?.[1] ?? ''
  activeIndex.value = 0
}
async function insert(item: CanvasReference, fromPicker = false) {
  if (props.disabled || !item.url) return
  const textarea = input.value?.textarea
  const from = fromPicker ? start.value : textarea?.selectionStart ?? props.modelValue.length
  const to = (fromPicker ? textarea?.selectionStart : textarea?.selectionEnd) ?? props.modelValue.length
  const text = `${item.mention} `
  emit('update:modelValue', props.modelValue.slice(0, from) + text + props.modelValue.slice(to))
  close()
  await nextTick()
  textarea?.focus()
  textarea?.setSelectionRange(from + text.length, from + text.length)
}
function keydown(event: KeyboardEvent) {
  if (event.isComposing) return
  if (open.value && ['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(event.key)) {
    event.preventDefault()
    event.stopPropagation()
    switch (event.key) {
      case 'ArrowDown': activeIndex.value = (activeIndex.value + 1) % matches.value.length; break
      case 'ArrowUp': activeIndex.value = (activeIndex.value - 1 + matches.value.length) % matches.value.length; break
      case 'Enter': void insert(matches.value[activeIndex.value]!, true); break
      case 'Escape': close(); break
    }
    return
  }
  emit('keydown', event)
}
</script>

<template>
  <div class="reference-input">
    <div v-if="showReferences && items.length" class="reference-strip" aria-label="参考素材">
      <button v-for="item in items" :key="item.id" type="button" class="reference-item" :disabled="disabled || !item.url"
        :title="`${item.label} · ${item.mention}`" :aria-label="`引用${item.label} ${item.mention}`" @mousedown.prevent @click="insert(item)">
        <video v-if="item.type === 'video'" :src="item.url || undefined" muted playsinline preload="metadata" />
        <img v-else :src="item.url || undefined" :alt="item.label" draggable="false" />
        <span>{{ item.mention }}</span><small>{{ item.label }}</small>
      </button>
    </div>
    <div class="reference-prompt">
      <MentionTextarea ref="input" :model-value="modelValue" :rows="rows" :disabled="disabled" :placeholder="placeholder"
        aria-label="生成提示词" @update:model-value="update" @keydown="keydown" @blur="close" />
      <div v-if="open" class="reference-picker" role="listbox" aria-label="选择引用素材">
        <button v-for="(item, index) in matches" :key="item.id" type="button" role="option" :aria-selected="activeIndex === index"
          :class="{ active: activeIndex === index }" @mousedown.prevent @click="insert(item, true)">
          <video v-if="item.type === 'video'" :src="item.url" muted playsinline preload="metadata" />
          <img v-else :src="item.url" :alt="item.label" />
          <span>{{ item.mention }} · {{ item.label }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.reference-input { min-width: 0; }
.reference-strip { display: flex; gap: 8px; overflow-x: auto; padding: 2px 2px 8px; }
.reference-item { flex: 0 0 72px; min-width: 0; padding: 4px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface-base); color: var(--color-text); cursor: pointer; text-align: left; }
.reference-item img, .reference-item video { display: block; width: 62px; height: 48px; object-fit: cover; border-radius: 4px; pointer-events: none; }
.reference-item span, .reference-item small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.reference-item small { color: var(--color-muted); }
.reference-item:hover, .reference-item:focus-visible { border-color: var(--color-primary); }
.reference-item:disabled { opacity: .5; cursor: default; }
.reference-prompt { position: relative; }
.reference-picker { position: absolute; bottom: calc(100% + 4px); left: 0; right: 0; z-index: 30; max-height: 220px; overflow: auto; padding: 4px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface-base); box-shadow: var(--shadow-soft); }
.reference-picker button { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px; border: 0; border-radius: 4px; background: transparent; color: var(--color-text); text-align: left; cursor: pointer; }
.reference-picker button.active, .reference-picker button:hover { background: var(--color-surface-soft); }
.reference-picker img, .reference-picker video { width: 36px; height: 32px; object-fit: cover; border-radius: 4px; pointer-events: none; }
</style>
