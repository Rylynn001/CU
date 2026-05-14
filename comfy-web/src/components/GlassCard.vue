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
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 20px;
  padding: 28px 32px;
  animation: breathe-glow 4s ease-in-out infinite, breathe-border 4s ease-in-out infinite;
  transition: background 0.3s ease;
}

.glass-card:hover {
  background: rgba(255, 255, 255, 0.05);
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
  background: #a78bfa;
  animation: pulse-dot 2.5s ease-in-out infinite;
  flex-shrink: 0;
}

.glass-card-title {
  margin: 0;
  font-size: 11px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 3px;
  text-transform: uppercase;
}
</style>
