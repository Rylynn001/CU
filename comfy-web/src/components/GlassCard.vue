<script setup lang="ts">
defineProps<{ title?: string }>()
</script>

<template>
  <div class="glass-card">
    <div v-if="$props.title" class="glass-card-header">
      <span class="breath-dot" />
      <h2 class="glass-card-title">{{ $props.title }}</h2>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.glass-card {
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  background: linear-gradient(180deg, rgba(32, 36, 48, 0.42), rgba(7, 9, 15, 0.28));
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 28px 32px;
  box-shadow: var(--shadow-soft);
  transition: background 0.3s ease, border-color 0.3s ease, transform 0.3s ease;
}

.glass-card:hover {
  background: linear-gradient(180deg, rgba(46, 50, 64, 0.5), rgba(9, 11, 18, 0.34));
  border-color: rgba(255, 255, 255, 0.24);
  transform: translateY(-2px);
}

.glass-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 22px;
}

.breath-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-primary);
  animation: pulse-dot 2.5s ease-in-out infinite;
  flex-shrink: 0;
}

.glass-card-title {
  margin: 0;
  font-size: 11px;
  font-weight: 500;
  color: var(--color-faint);
  letter-spacing: 0;
  text-transform: uppercase;
}
</style>
