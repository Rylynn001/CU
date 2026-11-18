<script setup lang="ts">
defineProps<{
  modelValue: string
  options: ReadonlyArray<{ value: string; label: string; width?: number; height?: number }>
  label: string
  disabled?: boolean
  showRatioShapes?: boolean
}>()

function ratioShapeStyle(option: { width?: number; height?: number }) {
  const width = option.width || 4
  const height = option.height || 3
  const scale = Math.min(20 / width, 16 / height)
  return { width: `${width * scale}px`, height: `${height * scale}px` }
}

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <div class="segmented-control" :class="{ 'ratio-control': showRatioShapes }" role="group" :aria-label="label">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      :class="{ active: modelValue === option.value, 'ratio-option': showRatioShapes }"
      :aria-pressed="modelValue === option.value"
      :disabled="disabled"
      @click="emit('update:modelValue', option.value)"
    >
      <span v-if="showRatioShapes" class="ratio-shape" :class="{ automatic: option.value === 'auto' }" :style="ratioShapeStyle(option)" aria-hidden="true" />
      {{ option.label }}
    </button>
  </div>
</template>

<style scoped>
.segmented-control {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(42px, 1fr));
  width: 100%;
  min-width: 0;
  gap: 3px;
  background: rgba(var(--color-white-rgb), 0.055);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 2px;
}

.segmented-control button {
  min-width: 0;
  padding: 5px 4px;
  background: none;
  border: none;
  color: var(--color-faint);
  font-size: 11px;
  line-height: 1.2;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.ratio-control { grid-template-columns: repeat(auto-fit, minmax(62px, 1fr)); }

.segmented-control button.ratio-option {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 34px;
  color: var(--color-text-soft);
}

.segmented-control button.ratio-option:hover:not(:disabled) { background: rgba(var(--color-white-rgb), 0.08); }

.ratio-shape {
  display: inline-block;
  box-sizing: border-box;
  flex-shrink: 0;
  border: 1px solid currentColor;
  border-radius: 2px;
}

.ratio-shape.automatic { border-style: dashed; }

.segmented-control button.active {
  background: rgba(var(--color-white-rgb), 0.1);
  color: var(--color-text);
  border-radius: 6px;
}

.segmented-control button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
