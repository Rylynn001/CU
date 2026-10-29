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
  display: inline-flex;
  background: rgba(var(--color-white-rgb), 0.055);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  padding: 2px;
}

.segmented-control button {
  padding: 5px 14px;
  background: none;
  border: none;
  color: var(--color-faint);
  font-size: 12px;
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
