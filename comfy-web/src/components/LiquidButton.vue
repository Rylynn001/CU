<script setup lang="ts">
import { computed } from 'vue'

defineOptions({
  inheritAttrs: false,
})

const props = withDefaults(defineProps<{
  type?: 'button' | 'submit' | 'reset'
  size?: 'sm' | 'md' | 'lg' | 'xl'
  disabled?: boolean
  loading?: boolean
  glowColor?: string
  glowSpeed?: string
}>(), {
  type: 'button',
  size: 'xl',
  disabled: false,
  loading: false,
  glowColor: 'rgba(255, 255, 255, 0.95)',
  glowSpeed: '4s',
})

const emit = defineEmits<{
  click: [event: MouseEvent]
}>()

const buttonStyle = computed(() => ({
  '--liquid-glow-color': props.glowColor,
  '--liquid-glow-speed': props.glowSpeed,
}))

function handleClick(event: MouseEvent) {
  if (props.disabled || props.loading) {
    event.preventDefault()
    return
  }

  emit('click', event)
}
</script>

<template>
  <button
    v-bind="$attrs"
    class="liquid-button"
    :class="[`liquid-button-${props.size}`, { 'is-loading': props.loading }]"
    :style="buttonStyle"
    :type="props.type"
    :disabled="props.disabled || props.loading"
    @click="handleClick"
  >
    <span class="liquid-border-track" />

    <span class="liquid-inner">
      <span class="liquid-shadow" />
      <span class="liquid-glass" />
      <span class="liquid-highlight" />
      <span class="liquid-content">
        <slot />
      </span>
    </span>
  </button>
</template>

<style scoped>
.liquid-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  overflow: hidden;
  border: none;
  border-radius: 999px;
  padding: 0;
  background: transparent;
  color: var(--color-text);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1;
  cursor: pointer;
  isolation: isolate;
  transition: transform 0.3s ease, border-color 0.3s ease, color 0.3s ease, opacity 0.2s ease;
}

.liquid-button:hover:not(:disabled) {
  transform: scale(1.05);
  color: #fff;
}

.liquid-button:active:not(:disabled) {
  transform: scale(0.98);
}

.liquid-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.liquid-button-sm {
  font-size: 12px;
}

.liquid-button-sm .liquid-inner {
  min-height: 30px;
  padding: 0 16px;
}

.liquid-button-md .liquid-inner {
  min-height: 38px;
  padding: 0 22px;
}

.liquid-button-lg .liquid-inner {
  min-height: 46px;
  padding: 0 28px;
}

.liquid-button-xl .liquid-inner {
  min-height: 54px;
  padding: 0 36px;
}

.liquid-border-track {
  position: absolute;
  z-index: 0;
  inset: 0;
  overflow: hidden;
  border-radius: inherit;
  padding: 2px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.25s ease;
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  mask-composite: exclude;
}

.liquid-button:hover:not(:disabled) .liquid-border-track {
  opacity: 0.95;
}

.liquid-border-track::before {
  content: '';
  position: absolute;
  inset: -50%;
  background:
    conic-gradient(
      from 0deg,
      transparent 0deg,
      transparent 72deg,
      var(--liquid-glow-color) 98deg,
      transparent 124deg,
      transparent 180deg,
      transparent 252deg,
      var(--liquid-glow-color) 278deg,
      transparent 304deg,
      transparent 360deg
    );
  animation: liquid-border-spin var(--liquid-glow-speed) linear infinite;
  animation-play-state: paused;
}

.liquid-button:hover:not(:disabled) .liquid-border-track::before {
  animation-play-state: running;
}

.liquid-inner {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: inherit;
}

.liquid-button:hover:not(:disabled) .liquid-inner {
  border-color: rgba(255, 255, 255, 0.48);
}

.liquid-shadow {
  position: absolute;
  inset: 0;
  z-index: -1;
  border-radius: inherit;
  box-shadow:
    0 10px 28px rgba(0, 0, 0, 0.12),
    inset 1px 1px 1px rgba(255, 255, 255, 0.5),
    inset -1px -1px 1px rgba(255, 255, 255, 0.16),
    inset 0 0 14px rgba(255, 255, 255, 0.045);
}

.liquid-glass {
  position: absolute;
  inset: 0;
  z-index: -1;
  overflow: hidden;
  border-radius: inherit;
  background: rgba(255, 255, 255, 0.035);
  backdrop-filter: blur(7px) saturate(135%);
  -webkit-backdrop-filter: blur(7px) saturate(135%);
}

.liquid-highlight {
  position: absolute;
  inset: 1px;
  z-index: -1;
  border-radius: inherit;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.22), transparent 44%, rgba(255, 255, 255, 0.08));
  opacity: 0.5;
  pointer-events: none;
  transition: opacity 0.3s ease;
}

.liquid-button:hover:not(:disabled) .liquid-highlight {
  opacity: 0.78;
}

.liquid-content {
  position: relative;
  z-index: 2;
}

.is-loading {
  animation: liquid-button-breathe 2s ease-in-out infinite;
}

@keyframes liquid-button-breathe {
  0%, 100% { opacity: 0.72; }
  50% { opacity: 1; }
}

@keyframes liquid-border-spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}
</style>
