<script setup lang="ts">
defineProps<{
  modelValue: string
  options: ReadonlyArray<{ value: string; label: string }>
  label: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <div class="segmented-control" role="group" :aria-label="label">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      :class="{ active: modelValue === option.value }"
      :aria-pressed="modelValue === option.value"
      :disabled="disabled"
      @click="emit('update:modelValue', option.value)"
    >{{ option.label }}</button>
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
